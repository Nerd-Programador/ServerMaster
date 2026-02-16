#!/usr/bin/env python3
"""Gera dados de simulação para IoT no SQLite e (opcional) publica no MQTT.

Uso rápido:
  python scripts/simulate_data.py --devices 5
  python scripts/simulate_data.py --devices 8 --loop --interval 5
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

DB_PATH = Path(__file__).resolve().parents[1] / "servermaster.db"


def ensure_db() -> None:
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
        conn.commit()


def upsert_device(conn: sqlite3.Connection, device_id: str, hostname: str, ip_address: str, status: str) -> None:
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
        (device_id, hostname, ip_address, datetime.now().isoformat(), status),
    )


def generate_devices(total: int) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for index in range(1, total + 1):
        room = random.choice(["sala", "quarto", "cozinha", "garagem", "escritorio"])
        status = random.choice(["online", "online", "online", "offline"])
        devices.append(
            {
                "device_id": f"esp-{index:02d}-{room}",
                "hostname": f"ESP-{room.capitalize()}-{index:02d}",
                "ip": f"192.168.0.{120 + index}",
                "status": status,
            }
        )
    return devices


def save_devices(devices: list[dict[str, str]]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        for dev in devices:
            upsert_device(conn, dev["device_id"], dev["hostname"], dev["ip"], dev["status"])
        conn.commit()


def publish_mqtt(devices: list[dict[str, str]], host: str, port: int, topic: str) -> None:
    if mqtt is None:
        print("[aviso] paho-mqtt não está instalado. Pulando publicação MQTT.")
        return

    client = mqtt.Client(client_id="servermaster-simulator")
    client.connect(host, port, keepalive=30)

    for dev in devices:
        final_topic = topic.replace("+", dev["device_id"])
        client.publish(final_topic, json.dumps(dev), qos=0, retain=False)

    client.disconnect()


def run_once(args: argparse.Namespace) -> None:
    ensure_db()
    devices = generate_devices(args.devices)
    save_devices(devices)
    if args.publish_mqtt:
        publish_mqtt(devices, args.mqtt_host, args.mqtt_port, args.mqtt_topic)

    print(f"[ok] {len(devices)} dispositivos simulados atualizados em {DB_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulador de dados para ServerMaster")
    parser.add_argument("--devices", type=int, default=5, help="Quantidade de ESPs simuladas")
    parser.add_argument("--loop", action="store_true", help="Atualiza continuamente")
    parser.add_argument("--interval", type=int, default=5, help="Intervalo em segundos no modo --loop")
    parser.add_argument("--publish-mqtt", action="store_true", help="Também publica em broker MQTT")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-topic", default="devices/+/status")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.loop:
        print("[info] simulador em loop. Ctrl+C para parar.")
        while True:
            run_once(args)
            time.sleep(args.interval)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
