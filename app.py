import json
import os
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from flask import Flask, jsonify, render_template

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - optional for development
    mqtt = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "servermaster.db"

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "devices/+/status")
FIREBASE_HOST = os.getenv("FIREBASE_HOST", "firebase.google.com")

app = Flask(__name__)



@dataclass
class ServiceStatus:
    name: str
    online: bool
    latency_ms: float | None


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iot_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE NOT NULL,
                hostname TEXT,
                ip_address TEXT,
                last_seen TEXT NOT NULL,
                status TEXT DEFAULT 'online'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS network_usage (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_month TEXT NOT NULL,
                upload_bytes INTEGER NOT NULL,
                download_bytes INTEGER NOT NULL,
                last_tx_bytes INTEGER NOT NULL,
                last_rx_bytes INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS network_monthly_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT UNIQUE NOT NULL,
                upload_bytes INTEGER NOT NULL,
                download_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


class NetworkUsageTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _ensure_seed(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT id FROM network_usage WHERE id = 1").fetchone()
        if row:
            return

        counters = psutil.net_io_counters()
        month_key = datetime.now().strftime("%Y-%m")
        conn.execute(
            """
            INSERT INTO network_usage (
                id, current_month, upload_bytes, download_bytes,
                last_tx_bytes, last_rx_bytes, updated_at
            ) VALUES (1, ?, 0, 0, ?, ?, ?)
            """,
            (month_key, counters.bytes_sent, counters.bytes_recv, datetime.now().isoformat()),
        )

    def update(self) -> dict[str, Any]:
        with self._lock, sqlite3.connect(DB_PATH) as conn:
            self._ensure_seed(conn)
            row = conn.execute(
                """
                SELECT current_month, upload_bytes, download_bytes,
                       last_tx_bytes, last_rx_bytes
                FROM network_usage WHERE id = 1
                """
            ).fetchone()

            if row is None:
                raise RuntimeError("Network usage row missing after seed")

            current_month, upload_total, download_total, last_tx, last_rx = row
            now = datetime.now()
            month_key = now.strftime("%Y-%m")

            counters = psutil.net_io_counters()
            delta_up = max(0, counters.bytes_sent - last_tx)
            delta_down = max(0, counters.bytes_recv - last_rx)

            upload_total += delta_up
            download_total += delta_down

            if now.day == 1 and current_month != month_key:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO network_monthly_history
                    (month_key, upload_bytes, download_bytes, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (current_month, upload_total, download_total, now.isoformat()),
                )
                conn.execute(
                    """
                    DELETE FROM network_monthly_history
                    WHERE id NOT IN (
                        SELECT id FROM network_monthly_history
                        ORDER BY month_key DESC LIMIT 12
                    )
                    """
                )
                upload_total = 0
                download_total = 0
                current_month = month_key

            conn.execute(
                """
                UPDATE network_usage
                SET current_month = ?, upload_bytes = ?, download_bytes = ?,
                    last_tx_bytes = ?, last_rx_bytes = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    current_month,
                    upload_total,
                    download_total,
                    counters.bytes_sent,
                    counters.bytes_recv,
                    now.isoformat(),
                ),
            )
            conn.commit()

            history_rows = conn.execute(
                """
                SELECT month_key, upload_bytes, download_bytes
                FROM network_monthly_history
                ORDER BY month_key DESC LIMIT 12
                """
            ).fetchall()

        history = [
            {
                "month": month,
                "upload_bytes": up,
                "download_bytes": down,
            }
            for month, up, down in history_rows
        ]

        return {
            "current_month": current_month,
            "upload_bytes": upload_total,
            "download_bytes": download_total,
            "history": history,
        }


network_tracker = NetworkUsageTracker()


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def format_uptime_human(total_seconds: int) -> str:
    units = [
        (30 * 24 * 3600, "MO"),
        (7 * 24 * 3600, "WK"),
        (24 * 3600, "DD"),
        (3600, "HH"),
        (60, "MM"),
        (1, "SS"),
    ]

    values: list[str] = []
    remainder = total_seconds
    for size, label in units:
        part = remainder // size
        remainder %= size
        if part > 0 or values:
            values.append(f"{int(part):02d}{label}")

    return " : ".join(values or ["00SS"])


def get_cpu_temperature() -> float | None:
    sensors = psutil.sensors_temperatures()
    if not sensors:
        return None
    for entries in sensors.values():
        if entries:
            return entries[0].current
    return None


def get_gpu_temperature() -> float | None:
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    output = result.stdout.strip()
    if "=" not in output:
        return None

    value = output.split("=")[-1].replace("'C", "")
    try:
        return float(value)
    except ValueError:
        return None


def ping_tcp(host: str, port: int, timeout: float = 1.5) -> float | None:
    start = time.perf_counter()
    try:
        with closing(socket.create_connection((host, port), timeout=timeout)):
            pass
    except OSError:
        return None
    return (time.perf_counter() - start) * 1000


def collect_service_status() -> list[ServiceStatus]:
    sqlite_online = DB_PATH.exists()
    return [
        ServiceStatus("INTERNET", ping_tcp("8.8.8.8", 53) is not None, ping_tcp("8.8.8.8", 53)),
        ServiceStatus("MQTT", ping_tcp(MQTT_BROKER, MQTT_PORT) is not None, ping_tcp(MQTT_BROKER, MQTT_PORT)),
        ServiceStatus("FIREBASE", ping_tcp(FIREBASE_HOST, 443) is not None, ping_tcp(FIREBASE_HOST, 443)),
        ServiceStatus("SQLITE", sqlite_online, 0.2 if sqlite_online else None),
    ]


def get_nas_disks() -> list[dict[str, Any]]:
    disks: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        mount = part.mountpoint
        if mount == "/":
            continue
        if mount.startswith(("/boot", "/run", "/snap")):
            continue
        try:
            usage = psutil.disk_usage(mount)
        except PermissionError:
            continue
        disks.append(
            {
                "device": part.device,
                "mountpoint": mount,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    return disks


def upsert_iot_device(device_id: str, hostname: str | None, ip: str | None, status: str = "online") -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO iot_devices (device_id, hostname, ip_address, last_seen, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                hostname = excluded.hostname,
                ip_address = excluded.ip_address,
                last_seen = excluded.last_seen,
                status = excluded.status
            """,
            (device_id, hostname, ip, datetime.now().isoformat(), status),
        )
        conn.commit()


def mqtt_message_handler(_: Any, __: Any, msg: Any) -> None:
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    topic_parts = msg.topic.split("/")
    topic_device_id = topic_parts[1] if len(topic_parts) >= 2 else "unknown-device"

    upsert_iot_device(
        device_id=payload.get("device_id", topic_device_id),
        hostname=payload.get("hostname", topic_device_id),
        ip=payload.get("ip"),
        status=payload.get("status", "online"),
    )


def start_mqtt_listener() -> None:
    if mqtt is None:
        return

    client = mqtt.Client(client_id="servermaster-dashboard")
    client.on_message = mqtt_message_handler

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except OSError:
        return

    client.subscribe(MQTT_TOPIC)
    client.loop_start()


@app.route("/")
def dashboard() -> str:
    return render_template("index.html", host_name=socket.gethostname())


@app.route("/api/metrics")
def api_metrics() -> Any:
    vm = psutil.virtual_memory()
    cpu_usage = psutil.cpu_percent(interval=0.2)
    uptime = int(time.time() - psutil.boot_time())
    cpu_temp = get_cpu_temperature()
    gpu_temp = get_gpu_temperature()
    network_usage = network_tracker.update()

    services = [
        {
            "name": svc.name,
            "online": svc.online,
            "latency_ms": round(svc.latency_ms, 2) if svc.latency_ms is not None else None,
        }
        for svc in collect_service_status()
    ]

    return jsonify(
        {
            "system": {
                "hostname": socket.gethostname(),
                "cpu_percent": cpu_usage,
                "memory_percent": vm.percent,
                "memory_used": format_bytes(vm.used),
                "memory_total": format_bytes(vm.total),
                "uptime_human": format_uptime_human(uptime),
                "temperature_cpu": cpu_temp,
                "temperature_gpu": gpu_temp,
                "network_upload": format_bytes(network_usage["upload_bytes"]),
                "network_download": format_bytes(network_usage["download_bytes"]),
                "network_current_month": network_usage["current_month"],
                "network_history": [
                    {
                        "month": month["month"],
                        "upload": format_bytes(month["upload_bytes"]),
                        "download": format_bytes(month["download_bytes"]),
                    }
                    for month in network_usage["history"]
                ],
            },
            "services": services,
            "nas": [
                {
                    **disk,
                    "total_h": format_bytes(disk["total"]),
                    "used_h": format_bytes(disk["used"]),
                    "free_h": format_bytes(disk["free"]),
                }
                for disk in get_nas_disks()
            ],
        }
    )


@app.route("/api/iot-devices")
def api_iot_devices() -> Any:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT device_id, hostname, ip_address, last_seen, status
            FROM iot_devices
            ORDER BY datetime(last_seen) DESC
            """
        ).fetchall()

    return jsonify(
        [
            {
                "device_id": d,
                "hostname": h,
                "ip_address": ip,
                "last_seen": ls,
                "status": st,
            }
            for d, h, ip, ls, st in rows
        ]
    )


init_db()
start_mqtt_listener()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
