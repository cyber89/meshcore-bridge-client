---
title: openHop Modem Overview
description: Device, firmware, flasher, and repeater integration docs for openHop Modem hardware.
---

openHop Modem turns supported ESP32-family and nRF52 LoRa boards into modem devices that can be driven by openHop Repeater over USB serial or over a LAN TCP connection.

The modem firmware owns the radio hardware and exposes a small control/data surface. The repeater still owns MeshCore routing, identities, storage, the dashboard, MQTT, sensors, and GPS integration.

## What this section covers

- Choosing a supported modem device
- Flashing firmware with the browser-based openHop MeshCore Flasher
- Provisioning Wi-Fi or Ethernet devices for TCP mode
- Selecting `modem_usb` or `modem_tcp` inside openHop Repeater
- Using the authenticated modem HTTP API
- Enabling modem diagnostics as a Repeater sensor
- Enabling modem HTTP GPS as Repeater's native GPS source

## Repositories and tools

- Modem firmware source and release assets: [openhop_modem](https://github.com/openhop-dev/openhop_modem)
- Browser flasher: [flasher.openhop.dev](https://flasher.openhop.dev/)

## Supported connection modes

| Mode | Repeater `radio_type` | Use when |
| --- | --- | --- |
| USB serial | `modem_usb` | The modem is plugged into the repeater host with USB. |
| Wi-Fi / Ethernet TCP | `modem_tcp` | The modem is on the LAN and exposes the openHop Modem binary protocol over TCP, normally on port `5055`. |

Networked modems with an HTTP API can also feed Repeater diagnostics and GPS through `/api/stats`. Those are separate from the RF transport: you can use `modem_tcp` for packets, `openhop_modem` for sensor telemetry, and `modem_http` for native GPS.

The USB/TCP host drivers live in openHop Core and openHop Repeater. This Modem
repository contains firmware and release assets rather than copied Python drivers
or Repeater packaging.

## Next steps

1. Pick a supported board in [Device Setup](/projects/openhop-modem/device-setup/).
2. Flash or update it using [Firmware Flasher](/projects/openhop-modem/flasher/).
3. Connect it to openHop Repeater using [Repeater Integration](/projects/openhop-modem/repeater-integration/).
4. For management integrations, read the [HTTP API Reference](/projects/openhop-modem/api/).
