---
title: Web Dashboard
description: Use the openHop Repeater dashboard for onboarding, monitoring, configuration, policy, and updates.
sidebar:
  order: 10
---

The CherryPy server provides the browser dashboard and authenticated REST API on
port 8000 by default:

```text
http://<repeater-ip>:8000
```

Keep it on a trusted LAN, VPN, or authenticated reverse proxy. The built-in API
authentication does not make direct public exposure a recommended deployment.

## What you can manage

Current builds expose setup and operational views for:

- **Monitoring:** Neighbors, Sessions, GPS, and Sensors;
- **Analytics:** Statistics, RF Health Correlation, Neighbour Links, Packet
  Archive, and Logs;
- **System → Configuration → Radio:** Radio Settings, Radio Hardware, Repeater,
  Duty Cycle, and TX Delays;
- **System → Configuration → Access:** Advert Limits, Regions/Keys, API Tokens,
  Web Options, Observer (MQTT), and Policies;
- **System → Configuration → Maintenance:** Backup, Database, and Memory;
- **System → Plugins:** external application installation and lifecycle;
- **Rooms, Companions:** Room Servers and Companions;
- stored neighbour region scopes and on-demand zero-hop scope queries;
- packet history and live WebSocket updates;
- configuration and hardware presets;
- radio settings, [CAD calibration](/projects/openhop-repeater/cad-calibration/),
  and noise-floor monitoring;
- policy and transport-key management;
- primary, room-server, and companion identities;
- logs, updates, and frontend selection.

**TX Delays** edits flood/direct TX delay factors. Both are randomized airtime
multipliers in the backend, even though the current UI labels direct delay as
seconds. The separate flood RX reception-quality control
(`delays.rx_delay_base`, disabled at `0`) is available through configuration/mesh
CLI, not this panel. See the
[Configuration Reference](/projects/openhop-repeater/config-file/#delays).

The exact cards shown depend on configured hardware and optional services. RRD
charts use `metrics.rrd` when RRD is enabled and available; otherwise chart APIs
can use SQLite-backed data.

## Authentication

The API is authenticated by default except for explicit setup and documentation
routes. Log in as `admin` with the configured admin password; mesh guest and
read-only settings do not provide guest dashboard access. The browser uses a
time-limited, refreshable JWT. API tokens can be created for trusted integrations
and are shown in plaintext only when created. They are administrator-equivalent,
not read-only tokens. See [Security and Authentication](/projects/openhop-repeater/security-and-authentication/).

- Change default/example passwords during setup.
- Store API tokens like passwords and revoke unused tokens.
- Leave CORS disabled unless a known browser client requires it.
- Do not share screenshots containing tokens, identity keys, location, or private
  network details.

## Plugins and application frontends

Open **System → Plugins** for **Installed** and **Catalogue** tabs. You can
install a catalogue release or upload a `.whl`, inspect status/logs, edit plugin
JSON settings, enable/disable, start/stop/restart service plugins, update, and
uninstall. Enabled UI-only applications show **UI READY** rather than RUNNING.
The uninstall dialog keeps persistent data by default; selecting data deletion
is destructive. Install/update progress can stream into the dialog.

A missing manager produces an unavailable/HTTP `503` state without stopping the
Repeater. An HTTP `504` with `outcome: unknown` is not cancellation: an install
may still finish. Refresh status before retrying.

Plugins are trusted code, not sandboxed extensions. Follow
[Plugins](/projects/openhop-repeater/plugins/) for a step-by-step dashboard walkthrough
covering catalogue installation, the Config gear, Open UI, updates, and removal.
For host setup and API automation, use
[Advanced Plugin Administration](/projects/openhop-repeater/plugin-administration/); package authors should use
[Plugin Development](/projects/openhop-repeater/plugin-development/).

## Maps

Current RepeaterUI maps need no provider key. Light mode uses OpenStreetMap
raster tiles; dark mode uses OpenFreeMap vector tiles and falls back to raster
if loading/WebGL fails. The map viewport and overlays survive theme changes.
The browser needs network access to the tile providers; an offline basemap is
not bundled. Older `carto_api_key` configuration can remain stored but is unused
by the current UI.

## API documentation

The repeater serves its own Swagger documentation under `/doc`. This central site
also publishes the synchronized [API Reference](/projects/openhop-repeater/api-reference/)
and raw spec at `/openapi/repeater.yaml`.

Interactive requests act on the selected server. Confirm the server URL and use
read-only endpoints first; configuration, identity, advert, calibration, update,
and control endpoints can mutate state or transmit.

## Configuration and restart behavior

Use **System → Configuration → Radio → Radio Hardware** for backend changes.
Changing `radio_type`, KISS
transport, or USB/TCP modem transport requires a service restart. If the UI is
unavailable, edit `/etc/openhop_repeater/config.yaml` carefully and use:

```bash
sudo systemctl restart openhop-repeater
sudo journalctl -u openhop-repeater -f
```

## Updates

Native installs can use the dashboard updater or `manage.sh upgrade`. Docker
installs must pull and recreate the container. Before any upgrade, back up the
configuration, identity, policy, and state data, including plugin data. Existing
native installations need one administrator-run updated `manage.sh upgrade` to
refresh the privileged OTA helper before relying on OTA plugin-manager
provisioning. Keep the standalone RepeaterUI and backend versions compatible;
the installed UI may differ from the latest development navigation described here.

## Implementation references

- [RepeaterUI navigation](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/config/navigation.ts)
- [Keyless map implementation](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/utils/mapTiles.ts)
- [Plugins dashboard](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/views/Plugins.vue)
