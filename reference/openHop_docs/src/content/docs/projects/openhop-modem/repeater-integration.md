---
title: Repeater Integration
description: Configure openHop Repeater to use an openHop Modem for RF, sensors, and GPS.
---

openHop Repeater can use an openHop Modem in three related ways:

1. As the RF transport with `radio_type: modem_usb` or `radio_type: modem_tcp`.
2. As a sensor source with `type: openhop_modem` under `sensors.definitions`.
3. As the native GPS source with `gps.source: modem_http`.

These are intentionally separate. For example, a TCP modem can carry packets on port `5055` while Repeater also polls `http://<modem-host>/api/stats` for battery, solar, and GPS diagnostics.

## Select the modem as Repeater's radio

Edit `/etc/openhop_repeater/config.yaml` and set the top-level `radio_type`. On a
new installation, the first-run setup flow can select it; after onboarding use
**System → Configuration → Radio → Radio Hardware** and restart.

### USB serial modem

Use this when the modem is plugged directly into the Repeater host.

```yaml
radio_type: modem_usb

modem_usb:
  port: "/dev/ttyACM0"
  baudrate: 921600
  lbt_enabled: true
  lbt_max_attempts: 5
```

If your board appears as `/dev/ttyUSB0`, use that instead.

### LAN TCP modem

Use this when the modem is reachable over Wi-Fi or Ethernet.

```yaml
radio_type: modem_tcp

modem_tcp:
  host: "REPLACE_WITH_MODEM_HOST"
  port: 5055
  token: ""
  connect_timeout: 5.0
  lbt_enabled: true
  lbt_max_attempts: 5
```

Replace `REPLACE_WITH_MODEM_HOST` with the board-specific mDNS hostname or LAN IP.
There is no generic `openhop-modem.local` hostname, and RAK4631 Ethernet does not
advertise mDNS. The TCP token is the modem protocol token, not the HTTP Basic Auth
password. Leave it empty only on a trusted LAN when the modem is configured that way.

## Keep radio settings aligned

The modem owns the physical SX1262 interface, but Repeater still sends the radio configuration it wants to use. Keep these values aligned with the mesh network:

```yaml
radio:
  frequency: 869618000
  tx_power: 22
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
  sync_word: 18
  preamble_length: 16
```

`tx_power` is the SX1262 command power, not necessarily the antenna output.
Boards with a PA or FEM can produce materially higher RF output or enforce a
lower chip-drive ceiling. Verify the exact board policy, antenna, and legal
regional limits before transmitting.

## Add the modem sensor

The `openhop_modem` sensor polls the modem HTTP `/api/stats` endpoint and exposes diagnostics under Repeater's `/api/stats -> sensors` output.

Use it for modem-visible data such as:

- GPS enabled/seen state
- GPS fix status
- latitude, longitude, altitude
- satellites used and in view
- UTC date/time
- speed and course
- battery voltage and derived battery percent
- solar charge rate when the modem exposes it

Example:

```yaml
sensors:
  enabled: true
  poll_interval_seconds: 10.0
  definitions:
    - type: hardware_stats
      name: system-health
      enabled: true

    - type: openhop_modem
      name: modem
      enabled: true
      settings:
        host: "REPLACE_WITH_MODEM_HOST"
        port: 80
        endpoint: "/api/stats"
        scheme: "http"
        username: "admin"
        password: "REPLACE_WITH_PASSWORD"
        poll_interval_seconds: 60.0
        timeout_seconds: 2.0
```

Notes:

- Use the modem HTTP password here, not the Repeater dashboard password.
- Current openHop Modem firmware always requires HTTP Basic Auth. Setting
  `password: ""` only suppresses Repeater's Authorization header and results in
  HTTP 401; it is not a supported unauthenticated mode.
- Keep `poll_interval_seconds` around `60.0` for modem telemetry so stats polling does not contend with packet transport or GPS polling on weak Wi-Fi.
- The sensor is diagnostics only. It does not make Repeater's native `/api/gps` endpoint GPS-enabled by itself.

## Use the modem as native Repeater GPS

Use `gps.source: modem_http` when you want Repeater's native GPS subsystem to use the modem's parsed GPS payload. This powers `/api/gps`, `/api/stats -> gps`, GPS diagnostics, optional GPS adverts, and optional config persistence.

The standard RAK4631 WisMesh Ethernet build does not expose GPS unless its
serial GPS support is explicitly compiled and configured. An HTTP API being
available does not by itself mean that the modem has a GPS fix source.

Example:

```yaml
gps:
  enabled: true
  source: modem_http
  host: "REPLACE_WITH_MODEM_HOST"
  port: 80
  endpoint: "/api/stats"
  scheme: "http"
  username: "admin"
  password: "REPLACE_WITH_PASSWORD"
  poll_interval_seconds: 2.0

  api_fallback_to_config_location: true
  advertise_gps_location: false
  persist_gps_fix_to_config: false
  stale_after_seconds: 10.0
  retain_sentences: 25
```

Supported values are:

- `modem_http`
- `http` (compatibility alias)

Prefer `modem_http` in new configs because it describes the integration boundary rather than one board.

## Sensor vs GPS source

| Config | Endpoint affected | Purpose |
| --- | --- | --- |
| `sensors.definitions[].type: openhop_modem` | `/api/stats -> sensors` | Diagnostics and telemetry cards. |
| `gps.source: modem_http` | `/api/gps` and `/api/stats -> gps` | Native Repeater GPS location, fix, satellite diagnostics, and optional GPS adverts. |

For a GPS-capable modem, it is normal to enable both. Use the sensor for battery/solar/modem diagnostics and use `modem_http` GPS for Repeater's own location model.

## Restart and verify

After editing the config:

```bash
sudo systemctl restart openhop-repeater
sudo journalctl -u openhop-repeater -f
```

Check the modem HTTP API directly from the Repeater host:

```bash
curl -u admin:REPLACE_WITH_PASSWORD http://REPLACE_WITH_MODEM_HOST/api/stats
```

Check Repeater's API:

```bash
curl http://localhost:8000/api/stats
curl http://localhost:8000/api/gps
```

Look for:

- successful `modem_usb` or `modem_tcp` modem connection in logs
- no serial permission errors for USB mode
- no placeholder host or DNS errors for TCP mode
- a `modem` sensor entry under `/api/stats -> sensors`
- GPS `source` showing modem HTTP when `gps.source: modem_http` is enabled
- satellite `in_view` records with azimuth/elevation/SNR when the modem exposes them

## Related pages

- [Device Setup](/projects/openhop-modem/device-setup/)
- [Firmware Flasher](/projects/openhop-modem/flasher/)
- [openHop Repeater Configuration Reference](/projects/openhop-repeater/config-file/)
- [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/)
