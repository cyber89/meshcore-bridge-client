---
title: HTTP API Reference
description: Read and configure network-capable openHop Modems through their authenticated LAN HTTP API.
---

Network-capable openHop Modems expose a small HTTP management API on port 80.
It is separate from the binary RF transport on TCP port 5055.

## Security boundary

The API uses HTTP Basic Authentication and does not provide TLS. Change the
factory/example password before trusting the device, and keep access on a trusted
LAN, VPN, or equivalent protected path. Do not expose the API directly to the
public Internet.

Use a board-specific hostname or LAN address:

```bash
curl -u admin:REPLACE_WITH_PASSWORD \
  http://REPLACE_WITH_MODEM_HOST/api/stats
```

The RAK4631 WisMesh Ethernet build uses DHCP but does not advertise mDNS.

## Read endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/temp` | Radio/device temperature data. |
| `GET` | `/api/system` | Firmware, board, uptime, and system state. |
| `GET` | `/api/radio` | Current radio parameters and RF status. |
| `GET` | `/api/network` | Wi-Fi/Ethernet and TCP-service state. |
| `GET` | `/api/stats` | Combined modem, radio, battery, GPS, and board diagnostics. |
| `GET` | `/api/gps` | GPS state and parsed payload when supported by the board and firmware build. |
| `GET` | `/api/config` | Current configurable management values. |

Responses vary by board capability. Station G3 includes PA/LNA controls and
INA219 telemetry. RAK4631 responses redact the TCP token and expose only whether
one is set; GPS fields are unavailable unless serial GPS support was compiled and
configured.

Station G3 `/api/stats` also exposes top-level `bus_voltage_v`, `current_ma`, and
`power_mw` from its INA219 input-power monitor. The `system` object (and
`/api/system`) has board-specific readings including
`station_g3_input_voltage_v`, `station_g3_current_ma`, `station_g3_power_w`,
minimum input voltage, and maximum current. Note the different power units:
`power_mw` is milliwatts, while `station_g3_power_w` is watts. Missing or failed
monitor readings are `null`, not measured zero. These are input-power readings,
not a battery-percentage estimate.

## Write endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/config` | Validate and persist supported configuration changes. |
| `POST` | `/api/reboot` | Schedule a device restart. |
| `POST` | `/dfu/ble` | RAK4631 Ethernet only: enter the installed Bluetooth DFU bootloader. |

A successful configuration save schedules a reboot where required. The RAK
`/dfu/ble` action only enters the installed bootloader: it does not upload a
firmware image and does not create an ESP-style `/update` endpoint. Use the
matching `firmware.zip` with the supported nRF52 DFU workflow.

### Wi-Fi power-save configuration

On Wi-Fi-capable boards, `GET /api/config` includes `wifi_power_save` (default
`true`). `POST /api/config` accepts a boolean of the same name; `false` disables
Wi-Fi modem sleep for lower latency at higher power draw. The change applies
after the post-save reboot. Non-Wi-Fi variants do not expose the setting and
reject unsupported configuration fields rather than enabling Wi-Fi.

These fields follow Modem dev
[`b95a809`](https://github.com/openhop-dev/openhop_modem/blob/b95a809e6ae37260dc146d59d25f63132962f63f/API.md).
Use the installed firmware's capabilities rather than assuming every published
board image has the latest source features.

## API and packet transport are independent

- HTTP management normally uses port 80 and Basic Auth.
- RF packet transport normally uses TCP port 5055 and its own optional token.
- The HTTP password and TCP token are different credentials.
- Repeater can use TCP for packets while independently polling `/api/stats` for
  sensor telemetry and GPS.

See [Repeater Integration](/projects/openhop-modem/repeater-integration/) for the
matching Repeater configuration.
