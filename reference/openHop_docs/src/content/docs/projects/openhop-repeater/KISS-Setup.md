---
title: KISS Setup
description: Configure openHop Repeater to use a serial KISS modem instead of GPIO radio hardware.
sidebar:
  order: 7
---

Use this mode when the repeater should talk to a serial KISS TNC rather than directly controlling SX1262 GPIO and SPI hardware.

## When to use it

Choose KISS mode if:

- the radio is already handled by external modem firmware
- the host only needs a serial connection to the modem
- you do not want GPIO pin mapping on the repeater host

If you are flashing a compatible MeshCore device for this role, the official [MeshCore.io Flasher](https://flasher.meshcore.io/) now has a KISS firmware option you can select before setting up the repeater host.

Set the backend with:

```yaml
radio_type: kiss
```

## Minimal config

```yaml
radio_type: kiss

kiss:
  port: "/dev/ttyUSB0"
  baud_rate: 9600

radio:
  frequency: 915000000
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
```

The main config file is `/etc/openhop_repeater/config.yaml`.

Frequency/bandwidth values are in Hz and must match your mesh and local rules;
this is an example, not a regional recommendation. KISS uses `baud_rate`, whereas
the openHop USB backend uses `baudrate`.

## Optional KISS timing

Repeater passes these optional settings to compatible KISS firmware. Omit them
to retain wrapper/firmware defaults; these are tuning examples from the canonical
config, not universally applied defaults:

```yaml
kiss:
  port: "/dev/ttyUSB0"
  baud_rate: 9600
  kiss_persistence: 255
  kiss_slottime_ms: 20
  tx_delay_ms: 50
  # kiss_txtail_ms: 0
  # kiss_full_duplex: false
```

`kiss_persistence: 255` removes probabilistic waiting once the channel is clear;
carrier sensing remains enabled. Repeater already staggers retransmissions, so
additional firmware CSMA/key-up delay can add latency. Full duplex disables
carrier-sense/CSMA and is not recommended as a latency workaround. Test changes
against actual firmware behavior and measured airtime.

## Using the setup helper

The repo helper supports KISS mode directly:

```bash
sudo bash setup-radio-config.sh /etc/openhop_repeater
```

During the prompts:

1. Select `KISS modem`
2. Choose the radio preset that matches the network
3. Enter the modem serial device, usually `/dev/ttyUSB0`
4. Enter the modem baud rate, usually `9600` unless your modem expects something else

Back up first. This legacy helper edits YAML with text substitutions; when a
`kiss:` section already exists, its `port`/`baud_rate` replacements can also alter
unrelated HTTP/GPS settings. Review those values before restarting, or use the
browser configuration instead.

## Serial device access

The repeater service user must be able to open the modem device.

Common checks:

```bash
ls -l /dev/ttyUSB0
id repeater
```

If needed, make sure the service user is in the correct serial-access group such as `dialout`.

Use a stable host device name when available. Docker short-form device mappings
cannot use colon-containing ESP32-S3 `/dev/serial/by-id/` names; a matching host
udev rule can provide `/dev/openhop-modem` instead. See
[Docker Deployment](/projects/openhop-repeater/docker/#usb-serial-device-names).

## What KISS changes

When using KISS:

- `sx1262` GPIO pin mappings are not the active radio path
- the modem handles the radio hardware layer
- you still configure repeater behavior, mesh behavior, storage, MQTT, GPS, and web settings in the same config file

## Restart and verify

```bash
sudo systemctl restart openhop-repeater
sudo journalctl -u openhop-repeater -f
```

If startup fails, check for:

- wrong serial device path
- wrong baud rate
- permissions on `/dev/ttyUSB0`
- a modem firmware that does not expose KISS correctly

## Related pages

- [Configuration Reference](/projects/openhop-repeater/config-file/)
- [Installation](/projects/openhop-repeater/installation/)
- [Hardware Setup](/projects/openhop-repeater/hardware-setup/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
