---
title: Device Setup
description: Choose, connect, and provision an openHop Modem device.
---

openHop Modem firmware supports multiple boards from the same `openhop_modem` source tree. Pick the firmware variant that matches the exact board, flash it, then choose whether the repeater will talk to it over USB or over TCP.

## Supported boards

| Device | Firmware environment | Network path |
| --- | --- | --- |
| Heltec WiFi LoRa 32 V3 | `heltec_v3` | Wi-Fi TCP + USB serial |
| Heltec WiFi LoRa 32 V4 | `heltec_v4` | Wi-Fi TCP + USB serial |
| Heltec WiFi LoRa 32 V4.2 | `heltec_v42` | Wi-Fi TCP + USB serial |
| Heltec WiFi LoRa 32 V4.3 | `heltec_v43` | Wi-Fi TCP + USB serial |
| Heltec Wireless Tracker V2 | `heltec_tracker_v2` | Wi-Fi TCP + USB serial |
| Ikoka Stick | `ikoka_stick` | Wi-Fi TCP + USB serial |
| Seeed XIAO Wio-SX1262 | `xiao_wio_sx1262` | Wi-Fi TCP + USB serial |
| MeshSmith Photon-1W ESP32-C6 | `photon_1w_xiao_esp32c6` | Wi-Fi TCP + USB serial |
| LilyGO T-LoRa T3-S3 v1.2/v1.3 | `lilygo_t3s3` | Wi-Fi TCP + USB serial |
| LilyGO T-Beam-S3 Supreme | `lilygo_tbeam_s3_supreme` | Wi-Fi TCP + USB serial |
| RAK3112 WisMesh | `rak3112_wismesh` | Wi-Fi TCP + USB serial |
| B&Q Consulting Station G2 | `station_g2` | Wi-Fi TCP + USB serial |
| BQ Voyage Station G3 | `station_g3` | Wi-Fi TCP + USB serial |
| WaveShare ESP32-P4-Nano | `esp32_p4_nano` | Ethernet or Wi-Fi TCP + USB flashing/debug paths |
| MeshSmith EtherMesh-1W | `ethermesh_1w` | Ethernet TCP + USB-UART flashing/debug |
| Heltec T114 | `heltec_t114` | USB serial only |
| RAK4631 USB | `rak4631_usb` | USB serial only |
| Seeed XIAO nRF52840 + Wio-SX1262 | `xiao_nrf52_wio` | USB serial only |
| RAK4631 WisMesh Ethernet Gateway | `rak4631_wismesh_eth` | Ethernet TCP + USB serial fallback |
| RAKwireless RAK3401 + RAK13302 | `rak3401` | USB serial only |

Use the hosted flasher for supported published targets: [flasher.openhop.dev](https://flasher.openhop.dev/).
Some targets and recovery paths still require PlatformIO, esptool, or nRF52 DFU.
For source builds, see the [openhop_modem repository](https://github.com/openhop-dev/openhop_modem).

## USB serial mode checklist

Use USB mode when the modem is physically attached to the repeater host.

1. Flash the board with the matching openHop Modem firmware.
2. Connect the board to the repeater host over USB.
3. Find the serial device:

```bash
ls -la /dev/serial/by-id/* /dev/ttyACM* /dev/ttyUSB*
```

4. Configure Repeater with `radio_type: modem_usb` and the detected port.

Typical ports:

- `/dev/ttyACM0` for native USB-CDC boards
- `/dev/ttyUSB0` for USB-UART bridge boards

Prefer a stable `/dev/serial/by-id/...` path when the board exposes one.
Numbered device paths can change after reconnecting or rebooting.

If the Linux service user cannot open the device, fix group membership or add a udev rule before troubleshooting Repeater itself.

## TCP mode checklist

Use TCP mode when the modem is on the same LAN as the repeater host.

1. Flash the board with the matching openHop Modem firmware.
2. Provision Wi-Fi, or connect Ethernet on supported boards.
3. Confirm the modem's hostname or IP address.
4. Configure Repeater with `radio_type: modem_tcp`, `host`, and `port: 5055`.

On first boot, Wi-Fi-capable modems expose a setup access point named like
`openHop-Modem-XXXX`. Connect to it, open `http://192.168.4.1`, choose the Wi-Fi
network, save, and let the modem reboot.

The modem mDNS hostnames are board-specific and include the final MAC bytes. Examples include:

- `heltec-<mac3>.local`
- `heltec-v4-<mac3>.local`
- `heltec-v42-<mac3>.local`
- `heltec-v43-<mac3>.local`
- `heltec-tracker-v2-<mac3>.local`
- `ikoka-<mac3>.local`
- `xiao-wio-<mac3>.local`
- `photon-c6-<mac3>.local`
- `lilygo-t3s3-<mac3>.local`
- `lilygo-tbeam-s3-supreme-<mac3>.local`
- `rak3112-<mac3>.local`
- `station-g2-<mac3>.local`
- `station-g3-<mac3>.local`
- `p4nano-<mac3>.local`
- `ethermesh-1w-<mac3>.local`

The RAK4631 WisMesh Ethernet firmware does not provide mDNS. Find its DHCP
address from the router or network inventory and connect directly to that IP.
Its authenticated WebUI and API run on port `80` and can configure hostname,
DHCP/static networking, HTTP password, and the openHop TCP token. WebUI firmware
upload is disabled; use its supported Bluetooth DFU flow or USB DFU for recovery.

## HTTP management and diagnostics

Web-enabled ESP32 modems and the RAK4631 Ethernet modem expose an HTTP UI and
JSON API protected with Basic Auth. The RAK4631 uses its W5100S Ethernet stack
and does not provide mDNS or WebUI firmware upload.

Default credentials on first boot:

- user: `admin`
- password: `openhop`

`openhop` is only the fresh/default password. Change it from the modem web UI
after first setup. Normal firmware updates preserve the configured password; they
do not reset it to the default. The same HTTP API is used by Repeater's optional
`openhop_modem` sensor and `modem_http` GPS source.

Useful checks:

```bash
curl -u admin:REPLACE_WITH_PASSWORD http://<modem-host>/api/stats
curl -u admin:REPLACE_WITH_PASSWORD http://<modem-host>/
```

## Wi-Fi power save

Current dev firmware provides **Wi-Fi power save** in the modem WebUI's network
settings. It defaults to enabled, including on Station G2/G3; it is no longer a
Station-only hardcoded policy. Disabling it can reduce Wi-Fi latency at the cost
of higher power draw. Consider that tradeoff when investigating delayed TCP
packets or idle Wi-Fi connectivity, particularly on battery-powered deployments.

The setting is persisted and applies after the network-settings save/reboot.
Management clients can use the boolean `wifi_power_save` in `POST /api/config`.
Wi-Fi-capable boards expose it in `GET /api/config`; non-Wi-Fi boards do not
support it. It does not change LoRa modulation or RF power.

Source: [Wi-Fi configuration and startup](https://github.com/openhop-dev/openhop_modem/blob/b95a809e6ae37260dc146d59d25f63132962f63f/firmware/src/wifi_manager.cpp)
and [management API](https://github.com/openhop-dev/openhop_modem/blob/b95a809e6ae37260dc146d59d25f63132962f63f/firmware/src/ota_manager.cpp).
Check the installed firmware revision; source dev changes need not yet be in the
flasher's selected published assets.

## Network exposure

The modem network services are intended for LAN use. Do not port-forward the modem TCP service or HTTP management page to the public Internet. Use a VPN if the repeater and modem are not on the same private network.
