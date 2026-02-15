# ServerMaster Dashboard (Raspberry Pi 3)

Dashboard web minimalista e responsiva para monitorar:
- **Web/System**: CPU, memória, temperatura, rede, uptime humano, histórico de rede.
- **NAS**: espaço total/usado/livre dos volumes (ocultando `/` root).
- **IoT**: descoberta dinâmica de ESP32/ESP8266 via MQTT com persistência no SQLite.
- **Statusbar fixa**: INTERNET, MQTT, FIREBASE e SQLITE com latência.

## 1) Instalação no Raspberry Pi

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip avahi-daemon
```

> `avahi-daemon` permite acesso local via `ServerMaster.local`.

## 2) Projeto e dependências

```bash
git clone <SEU_REPO> /opt/servermaster-dashboard
cd /opt/servermaster-dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Variáveis de ambiente (opcional)

```bash
export MQTT_BROKER=127.0.0.1
export MQTT_PORT=1883
export MQTT_TOPIC="devices/+/status"
export FIREBASE_HOST="firebase.google.com"
```

## 4) Testar localmente

```bash
source .venv/bin/activate
python app.py
```

Abra:
- `http://localhost:5000`
- `http://ServerMaster.local:5000`

## 5) Subir como serviço systemd

Crie `/etc/systemd/system/servermaster-dashboard.service`:

```ini
[Unit]
Description=ServerMaster Dashboard
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/servermaster-dashboard
Environment="MQTT_BROKER=127.0.0.1"
Environment="MQTT_PORT=1883"
Environment="MQTT_TOPIC=devices/+/status"
Environment="FIREBASE_HOST=firebase.google.com"
ExecStart=/opt/servermaster-dashboard/.venv/bin/python /opt/servermaster-dashboard/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ative:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now servermaster-dashboard
sudo systemctl status servermaster-dashboard
```

Acesso final:
- `http://ServerMaster.local:5000`

> Se quiser sem `:5000`, use Nginx como proxy reverso para porta 80.

## 6) Integração IoT (ESP32/ESP8266 via MQTT)

Cada ESP deve publicar em um tópico compatível (default: `devices/<id>/status`) com payload JSON:

```json
{
  "device_id": "esp32-quarto",
  "hostname": "ESP-Quarto",
  "ip": "192.168.0.45",
  "status": "online"
}
```

Ao chegar uma mensagem:
- o card aparece automaticamente na seção **IoT**;
- dados ficam salvos no SQLite (`servermaster.db`).

## 7) Regras especiais implementadas

- **Uptime humano dinâmico**: formato progressivo com unidades (SS, MM, HH, DD, WK, MO).
- **Rede mensal**:
  - acumula upload/download com base em `psutil.net_io_counters()`;
  - no dia **01**, salva consumo do mês anterior;
  - mantém histórico dos últimos **12 meses**;
  - zera contadores para novo ciclo mensal.

## 8) Estrutura

```text
app.py
requirements.txt
templates/index.html
static/style.css
static/app.js
servermaster.db (gerado em runtime)
```
