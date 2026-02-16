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


### Modo demonstração (dados simulados na página)

Se você quiser ver a dashboard completa mesmo sem sensores/discos/MQTT reais:

```bash
SIMULATION_MODE=1 python app.py
```

No Windows (PowerShell):

```powershell
$env:SIMULATION_MODE = "1"
python app.py
```

Isso preenche CPU/memória/rede/NAS/status com valores simulados para facilitar validação visual.

## 4.1) Rodando localmente no VSCode (passo a passo)

Se você está começando agora, esse é o fluxo mais simples:

1. Abra a pasta do projeto no VSCode (`File > Open Folder`).
2. Abra o terminal integrado (`Ctrl + ``).
3. Crie o ambiente virtual:

```bash
python3 -m venv .venv
```

4. Ative o ambiente virtual:

```bash
source .venv/bin/activate
```

5. Instale as dependências:

```bash
pip install -r requirements.txt
```

6. Selecione o interpretador Python no VSCode:
   - `Ctrl + Shift + P`
   - `Python: Select Interpreter`
   - escolha o da pasta `.venv`

7. Rode a aplicação no terminal:

```bash
python app.py
```

8. Abra no navegador:
   - `http://localhost:5000`

### Executar com botão de Debug do VSCode (opcional)

Crie o arquivo `.vscode/launch.json` com:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "ServerMaster Dashboard",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/app.py",
      "console": "integratedTerminal",
      "env": {
        "MQTT_BROKER": "127.0.0.1",
        "MQTT_PORT": "1883",
        "MQTT_TOPIC": "devices/+/status",
        "FIREBASE_HOST": "firebase.google.com"
      }
    }
  ]
}
```

Depois disso, é só apertar `F5`.


## 4.2) Problema no Windows: `python3` não encontrado

Se aparecer erro como:

```text
Python não foi encontrado; executar sem argumentos para instalar do Microsoft Store...
```

no Windows normalmente o comando correto é `python` ou `py` (e não `python3`).

### Passo a passo (Windows + PowerShell)

1. Instale o Python 3.11+ pelo site oficial: https://www.python.org/downloads/windows/
2. **Marque** a opção `Add Python to PATH` durante a instalação.
3. Feche e abra o PowerShell novamente.
4. Teste:

```powershell
py --version
python --version
```

5. Crie a venv com um destes comandos:

```powershell
py -3 -m venv .venv
```

ou

```powershell
python -m venv .venv
```

6. Ative o ambiente virtual:

```powershell
.\.venv\Scripts\Activate.ps1
```

7. Se bloquear por política de execução, rode (uma vez):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

8. Instale dependências e rode:

```powershell
pip install -r requirements.txt
python app.py
```

> Dica: em Windows, não use `source .venv/bin/activate` (esse comando é para Linux/macOS).

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

## 6.1) Script de simulação de dados IoT

Criei um script para preencher o SQLite com ESPs fictícias e, opcionalmente, publicar no MQTT:

```bash
python scripts/simulate_data.py --devices 6
```

Modo contínuo (atualiza a cada 5s):

```bash
python scripts/simulate_data.py --devices 6 --loop --interval 5
```

Publicando também no MQTT:

```bash
python scripts/simulate_data.py --devices 6 --publish-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883
```

No Windows, use os mesmos comandos com `python` no PowerShell.

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
scripts/simulate_data.py
servermaster.db (gerado em runtime)
```
