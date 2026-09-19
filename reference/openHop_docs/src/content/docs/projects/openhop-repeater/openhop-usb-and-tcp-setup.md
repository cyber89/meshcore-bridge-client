---
title: openHop USB/TCP Setup
description: Configure openHop Repeater to use an openHop Modem over USB serial or TCP.
sidebar:
  order: 8
---

Use these modes when the radio hardware is already managed by a modem running openHop Modem firmware rather than by local SX1262 GPIO and SPI control.

For device selection, firmware flashing, HTTP diagnostics, modem sensors, and modem-backed GPS, see the [openHop Modem section](/projects/openhop-modem/).

## When to use each mode

- Use `radio_type: modem_usb` when the modem is plugged directly into the host over USB serial.
- Use `radio_type: modem_tcp` when the modem lives on another board and exposes a TCP service over LAN, Wi-Fi, or Ethernet.

Both modes keep the repeater in charge of node behavior, the dashboard, API, MQTT, GPS, identities, and storage.

The main config file is `/etc/openhop_repeater/config.yaml`.

## openHop Modem over USB serial

Minimal config:

```yaml
radio_type: modem_usb

modem_usb:
  port: "/dev/ttyACM0"
  baudrate: 921600
  lbt_enabled: true
  lbt_max_attempts: 5
```

The commented canonical config example uses these USB values:

- `port: /dev/ttyACM0`
- `baudrate: 921600`
- `lbt_enabled: true`
- `lbt_max_attempts: 5`

Checks:

```bash
ls -l /dev/ttyACM0
id repeater
```

Make sure the service user can open the USB serial device.

Prefer a stable host device name when available, and verify it after reconnects.
In Docker, map the actual device and use the container-side path in `modem_usb.port`.
Colon-containing ESP32-S3 by-id names cannot be used in short-form Docker device
mappings; see [USB serial device names](/projects/openhop-repeater/docker/#usb-serial-device-names).
In Proxmox LXC, passing `/dev/bus/usb` alone does not expose `/dev/ttyACM0`;
the serial character device needs its own passthrough and permissions.

## openHop Modem over TCP

Minimal config:

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

Use these TCP values as a starting point:

- `host: REPLACE_WITH_MODEM_HOST`
- `port: 5055`
- `token: ""`
- `connect_timeout: 5.0`
- `lbt_enabled: true`
- `lbt_max_attempts: 5`

Replace the placeholder with the modem LAN IP or its actual board-specific
hostname, such as `heltec-v4-<mac3>.local`. The Repeater source template's
`openhop-modem.local` value is only an example; current modem firmware generates
board-specific names and some Ethernet targets do not advertise mDNS at all.

The TCP token authenticates the modem connection but does not make it a TLS
tunnel. Keep the modem protocol on a trusted LAN/VPN; do not expose port 5055
directly to the internet. Modem HTTP diagnostics/GPS have their own host, port,
and credentials under `sensors`/`gps`; setting the radio TCP block alone does not
enable those optional pollers.

## Configure the backend

During first-run onboarding, use the browser setup flow:

```text
http://<repeater-ip>:8000/setup
```

After onboarding, `/setup` redirects to `/login`. Use **System → Configuration →
Radio → Radio Hardware**, or edit the `modem_usb` or `modem_tcp` block in
`/etc/openhop_repeater/config.yaml`, then restart Repeater. The terminal
`setup-radio-config.sh` helper does not currently configure these two backends.

## Radio settings that still matter

Even though the modem firmware owns the radio hardware, these repeater settings still need to match the network:

- `radio.frequency`
- `radio.tx_power`
- `radio.bandwidth`
- `radio.spreading_factor`
- `radio.coding_rate`
- `radio.preamble_length`

The canonical Repeater config currently defaults to:

- `tx_power: 14`
- `preamble_length: 32`

Hardware presets may intentionally override these values. Match the actual mesh
and regional rules rather than assuming either set is universal.

## Restart and verify

```bash
sudo systemctl restart openhop-repeater
sudo journalctl -u openhop-repeater -f
```

Look for:

- successful modem connection
- no placeholder-host errors for `modem_tcp`
- no permission errors on `/dev/ttyACM0` for `modem_usb`

## Related pages

- [Installation](/projects/openhop-repeater/installation/)
- [Hardware Setup](/projects/openhop-repeater/hardware-setup/)
- [Configuration Reference](/projects/openhop-repeater/config-file/)
- [openHop Modem Repeater Integration](/projects/openhop-modem/repeater-integration/)
- [KISS Setup](/projects/openhop-repeater/kiss-setup/)
