# MeshCore Bridge & Web Station

**Your MeshCore radio, browser dashboard, and automation gateway in one application.**

MeshCore Bridge connects a radio running **MeshCore Companion firmware** to a host over USB serial or TCP. It brings channel chat, direct messages, mesh visibility, radio administration, and telemetry into a web interface, then connects those events to MQTT workflows such as n8n and Home Assistant.

Run it on a Linux gateway or a Windows computer, open the dashboard from your browser, and manage the connected station without switching between separate tools.

[Get started](#get-started) · [Features](#what-you-can-do) · [Configuration](#configure-your-station) · [MQTT integration](#connect-your-automations) · [Documentation](#documentation)

## What you can do

| Area | Capabilities |
| --- | --- |
| **Chat** | Public and configured private channels, direct messages, message history, and delivery status where the protocol provides acknowledgements. |
| **Contacts and nodes** | A contact book for user devices and a unified mesh view for infrastructure, rooms, sensors, and nearby nodes, with link information and telemetry. |
| **Radio administration** | Local station settings and remote repeater administration, including supported radio parameters, identity, telemetry, neighbors, and command consoles. |
| **Maps and analytics** | Node positions, link quality, RF activity, airtime estimates, health metrics, logs, and packet inspection. Local MBTiles and XYZ tile storage support map use without downloading each tile. |
| **Automation** | Structured MQTT receive events, outgoing message requests, transmission status, and administrative commands. Optional external broker forwarding includes event filters and location privacy settings. |
| **Companion access** | A TCP Companion endpoint for compatible MeshCore mobile applications and CLI tools, with command arbitration for the shared radio. |
| **Web experience** | Responsive navigation, light and dark themes, live WebSocket updates, and a REST API with a locally served OpenAPI viewer. |

The radio remains the source of MeshCore protocol behavior. Available commands depend on its firmware and capabilities. Repeater devices belong to the node and administration views; they never appear as chat contacts or receive chat/DM requests. The local station cannot be a message destination.

### Efficient delivery and mesh operation

The browser receives committed, minified JavaScript/CSS and precompressed gzip assets when it supports them. Static files are compressed during the build, so serving them does not repeatedly spend CPU on compression. No Node.js installation is needed to run the station.

Selected analytics JSON responses use light compression outside the asyncio event loop, with an **average compression-worker budget of 50% of one CPU core**. This budget applies to compression work; brief peaks are possible, and it does not cap total bridge CPU usage. See [frontend delivery and compression](docs/FRONTEND_DELIVERY.md) for its scope.

Transmission pacing, priority queues, duplicate detection, reconnect handling, and airtime tracking help manage a shared LoRa channel. Airtime figures are estimates, and the operator chooses radio settings and operating limits appropriate to the network.

## Get started

You will need:

- A radio running MeshCore Companion firmware, connected with a USB data cable or reachable through a Companion TCP endpoint.
- **Stable CPython 3.12 or newer**, with virtual environment and pip support. **3.13.5 is recommended**; later stable versions are allowed, with no upper version limit. Check the selected interpreter's full version before installing; the host distribution's default Python may be older.
- A Linux host with APT and systemd for the automated Linux installer, or Windows with PowerShell for the Windows launcher.
- An MQTT broker for MQTT workflows. The Linux installer provisions Mosquitto; Windows and manual setups use a broker you provide.

Hardware support follows the Companion firmware and SDK, rather than a blanket guarantee for every board from a manufacturer. Verify your radio's firmware and connection before configuring the bridge.

### Linux: install as a service

Clone into a working directory separate from the installation destination:

```bash
git clone https://github.com/cyber89/meshcore-bridge-client.git "$HOME/meshcore-bridge-client"
cd "$HOME/meshcore-bridge-client"
sudo bash install.sh
```

The installer deploys to `/opt/meshcore-bridge`, creates a Python virtual environment, configures serial access, and registers and starts `meshcore-bridge.service`. It creates `.env` from the template when absent and preserves an existing configuration.

The initial installation also configures and starts Mosquitto with an anonymous listener on `0.0.0.0:1883`. Choose the broker's bind address, authentication, and firewall rules for your deployment. To configure the bridge before its first connection, use the manual setup below.

If your supported interpreter has a custom location, pass it explicitly:

```bash
sudo env MESHCORE_PYTHON=/path/to/python3.13 bash install.sh
```

Review the deployed configuration and restart after editing:

```bash
sudo nano /opt/meshcore-bridge/.env
sudo systemctl restart meshcore-bridge.service
sudo systemctl status meshcore-bridge.service
sudo journalctl -u meshcore-bridge.service -f
```

For subsequent releases, update your source checkout and apply the staged update:

```bash
cd "$HOME/meshcore-bridge-client"
git pull --ff-only
sudo bash install.sh --update
```

The update preserves `.env`, data, maps, and logs, and restarts the service. See the [deployment guide](docs/DEPLOYMENT_GUIDE.md) for custom storage paths and service configuration.

### Windows: install and launch

```powershell
git clone https://github.com/cyber89/meshcore-bridge-client.git
Set-Location meshcore-bridge-client
.\install.ps1 -InstallDeps
notepad .env
.\install.ps1 -Run
```

The launcher creates a local `.venv`, installs production dependencies, detects serial ports, and creates `.env` when absent. An existing `.env` is preserved. Set the correct `SERIAL_PORT` and MQTT connection before using `-Run`. The launcher runs the station in the current console; it does not install a Windows service or an MQTT broker.

### Manual setup

From the repository root on Linux, with a supported interpreter already installed:

```bash
python3.13 --version
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
# Edit .env before starting the station.
nano .env
python meshcore_bridge.py
```

On Windows, use the interpreter selected for your installation to create `.venv`, then activate it with `.\.venv\Scripts\Activate.ps1`. The production entry point is also available as `python -m src`.

## Configure your station

Configuration loads from `.env` in the repository or installation root; existing process environment variables take precedence. Use [.env.example](.env.example) as the full settings template. The values below describe the supplied template unless stated otherwise.

| Setting | Initial value | Purpose |
| --- | --- | --- |
| `SERIAL_PORT` | `AUTO` | USB port such as `/dev/ttyACM0`, a persistent `/dev/serial/by-id/...` path, `COM3`, or `tcp://host:port`. Without `.env`, the code defaults to `/dev/ttyACM0` on Linux and `AUTO` on Windows. |
| `BAUD_RATE` | `115200` | Serial connection speed. |
| `WEB_ENABLED` / `WEB_HOST` / `WEB_PORT` | `true` / `0.0.0.0` / `8080` | Enable the dashboard and API, and choose their listening address. |
| `BRIDGE_API_KEY` | Empty | Optional key for API writes, protected reads, WebSocket access, and API documentation. REST integrations use `X-Api-Key`. |
| `MQTT_BROKER` / `MQTT_PORT` | `127.0.0.1` / `1883` | Local automation broker address and port. |
| `MQTT_USER` / `MQTT_PASSWORD` | Empty | MQTT authentication when required by your broker. |
| `MQTT_TLS` | `false` | Enable TLS; configure the broker, port, and optional CA/client certificate paths for that listener, then restart. |
| `TOPIC_PREFIX` | `meshcore` | Root for local MQTT topics. |
| `TCP_SERVER_ENABLED` / `TCP_SERVER_PORT` | `true` / `5000` | Companion TCP endpoint; its initial bind address is `0.0.0.0`. |
| `COMPANION_ALLOWED_IPS` / `COMPANION_TOKEN` | Empty | Optional TCP client restrictions and authentication. |
| `DATA_DIR` / `LOG_DIR` | `data` / `logs` | Persistent data and rotating log directories. |
| `LOG_LEVEL` | `INFO` | Logging detail. |

Storage paths for channels, the node registry, and airtime history can be configured separately. When moving `DATA_DIR`, review those explicit paths in `.env` as well. Keep `.env` and your data backed up when changing deployment paths.

After startup, open **`http://localhost:8080`** on the host, or **`http://<host-ip>:8080`** from a device on your network. Select a channel or contact for chat, use Nodes for mesh and repeater operations, and use Settings to review station and integration configuration.

Local tiles belong under `DATA_DIR/maps/`: MBTiles files go directly in that directory and XYZ tiles under `maps/tiles/{z}/{x}/{y}`. The current map frontend loads Leaflet from a CDN; local tiles alone do not make the entire browser interface fully offline.

## Connect your automations

The local broker interface exposes JSON events for incoming traffic and accepts transmission requests. Use the [n8n workflow](n8n_workflow_meshcore.json) and [integration guide](docs/N8N_WORKFLOW_GUIDE.md) for payload formats and workflow setup. Home Assistant and other MQTT consumers can subscribe to the same topics; configure their entities and automations for the published schemas.

| Topic with the default prefix | Direction | Purpose |
| --- | --- | --- |
| `meshcore/bridge/state` | Bridge → broker | Retained online/offline state, including the MQTT last will. |
| `meshcore/bridge/health` | Bridge → broker | Periodic health metrics. |
| `meshcore/rx/all` | Bridge → broker | Unified receive-event stream. |
| `meshcore/rx/public` | Bridge → broker | Public channel messages. |
| `meshcore/rx/channel/ch_<index>` | Bridge → broker | Messages from secondary channels. |
| `meshcore/rx/direct/<sender>` | Bridge → broker | Direct messages grouped by sender. |
| `meshcore/rx/telemetry` / `meshcore/rx/nodes` | Bridge → broker | Telemetry and node discovery events. |
| `meshcore/tx` | Automation → bridge | Outgoing message requests. |
| `meshcore/tx/status` | Bridge → broker | Transmission results and supported acknowledgement events. |
| `meshcore/admin/cmd` / `meshcore/admin/repeater` | Automation → bridge | Administrative requests. |
| `meshcore/admin/status` | Bridge → broker | Administrative results. |

Start with receive-only subscriptions, then add deliberate outgoing actions. Avoid feeding every received message back into `meshcore/tx`; outgoing messages and administrative operations consume shared radio airtime.

## API and live events

The web server uses FastAPI/Uvicorn and shares state with the radio and MQTT pipeline.

| Interface | Address or route | Purpose |
| --- | --- | --- |
| Dashboard | `GET /` | Browser station interface. |
| API reference | `GET /docs` | Locally served, read-only OpenAPI viewer. `/redoc` is an alias for the same viewer. |
| API schema | `GET /openapi.json` | OpenAPI JSON for integration tools. |
| Live events | `ws://<host-ip>:8080/ws` | WebSocket event and message interface. |
| Health | `GET /api/health` | Bridge health and operating metrics. |
| Contacts | `GET /api/contacts` | Contact book excluding repeaters and the local station. |
| Messaging | `POST /api/tx` | Channel or direct message requests. |
| Repeater administration | `POST /api/admin/repeater` | Remote administrative operations. |
| Companion TCP | `tcp://<host-ip>:5000` | Shared-radio access for compatible Companion clients. |

When `BRIDGE_API_KEY` is configured, enter it in the documentation viewer or supply it through `X-Api-Key` when fetching the schema. The viewer displays the contract and does not execute API operations. Choose listening addresses and client access controls for the network where the station runs.

## Documentation

| Guide | Contents |
| --- | --- |
| [Documentation index](docs/README.md) | Authority, navigation, and the full technical documentation catalog. |
| [Deployment](docs/DEPLOYMENT_GUIDE.md) | Services, Python environments, serial permissions, brokers, and configuration. |
| [Architecture](docs/ARCHITECTURE.md) | Application components, event flow, and integration boundaries. |
| [Protocol specification](docs/PROTOCOL_SPEC.md) | MeshCore protocol contracts and framing. |
| [Domain model](CONTEXT.md) | Node roles, terminology, and application invariants. |
| [Frontend delivery](docs/FRONTEND_DELIVERY.md) | Minified assets, gzip delivery, and compression CPU budgeting. |
| [Testing](docs/TESTING.md) | Maintained checks, isolated fixtures, and verification scope. |

Some detailed technical guides are currently written in Spanish. **The root README and both installation scripts are maintained entirely in English**, including headings, comments, help, prompts, and status messages.

## Development

Production code is under `src/`, browser sources under `src/web/static/`, and maintained tests under `tests/`. Official firmware, SDK, and CLI snapshots under `reference/` are read-only protocol references. The root `requirements.txt` contains production dependencies; development tools are listed separately in `requirements-dev.txt`.

For frontend changes, rebuild the committed artifacts before publishing:

```bash
npm --prefix tools/frontend ci
npm --prefix tools/frontend run build
npm --prefix tools/frontend run check
```

Node.js 18 or newer is a development build requirement. Edit the original JS/CSS sources, then rebuild their minified and gzip variants; do not edit generated files directly.

The project support baseline is stable CPython 3.12+. CPython 3.13.5 is recommended, and later stable versions are allowed without an upper version limit. A version policy does not prove dependency availability or runtime behavior on every platform; record the actual interpreter and checks used. See [ADR 0016](docs/adr/0016-python-3-12-baseline.md) and [AGENTS.md](AGENTS.md).

Automated suites run only when explicitly requested under the project's [agent instructions](AGENTS.md). See [Testing](docs/TESTING.md) for isolated pytest, browser, coverage, typing, and lint workflows; do not use an operating station as a test fixture.
