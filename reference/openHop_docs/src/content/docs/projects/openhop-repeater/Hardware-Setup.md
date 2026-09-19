---
title: Hardware Setup
description: Supported openHop Repeater hardware and radio backend notes.
sidebar:
  order: 6
---

openHop Repeater supports more than just a Raspberry Pi with a GPIO-connected SX1262. The current repo supports five active backend classes plus a no-radio mode:

- Native `sx1262` over Linux SPI and host GPIO
- `sx1262_ch341` over a CH341 USB-SPI adapter
- `kiss` using a serial KISS TNC instead of GPIO radio control
- `modem_usb` using a USB serial modem running openHop Modem firmware
- `modem_tcp` using a network modem running openHop Modem firmware
- `null` or `none` when you want the daemon without RF hardware

## Supported hardware families

The repo currently includes named radio presets for families such as:

- HackerGadgets uConsole LoRa module variants
- PiMesh 1W variants
- Frequency Labs `meshadv-mini` and `meshadv`
- Zebra and Zebra Duo HAT variants
- NebraHat and NebraDuo variants
- Femtofox 1W/2W
- PineDio
- RAK6421/RAK13300 slot variants
- Zindello Industries UltraPeater and UltraPeaterZero variants
- Waveshare SX1262 SPI HAT
- CH341 USB-SPI + SX1262 combinations

Heltec `HT-RA62` and generic SX1262/E22-class hardware may work through custom
configuration, but they are not named presets in the current preset file.

For non-GPIO modem-style transports, use [KISS Setup](/projects/openhop-repeater/kiss-setup/) or [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/).

## Backend selection

Choose the backend with the top-level `radio_type` in `/etc/openhop_repeater/config.yaml`.

```yaml
radio_type: sx1262
```

Supported values:

- `sx1262`
- `sx1262_ch341`
- `kiss`
- `modem_usb`
- `modem_tcp`
- `null` or `none`

For `sx1262_ch341`, `modem_usb`, `modem_tcp`, or `null`, complete the initial
choice in `/setup`. After onboarding, use **System → Configuration → Radio →
Radio Hardware** or edit the config directly, then restart Repeater.

## Native SX1262 wiring

For a direct Linux SPI host, `sx1262` pins are host GPIO values.

```yaml
sx1262:
  bus_id: 0
  cs_id: 0
  cs_pin: 21
  reset_pin: 18
  busy_pin: 20
  irq_pin: 16
  txen_pin: -1
  rxen_pin: -1
  en_pin: -1
  txled_pin: -1
  rxled_pin: -1
  use_dio3_tcxo: false
  dio3_tcxo_voltage: 1.8
  use_dio2_rf: false
  is_waveshare: false
```

Typical Raspberry Pi SPI pins:

| Function | Raspberry Pi pin |
| --- | --- |
| MOSI | GPIO 10 / pin 19 |
| MISO | GPIO 9 / pin 21 |
| SCK | GPIO 11 / pin 23 |
| CS | Usually GPIO 21 or board-specific |

## CH341 USB-SPI hosts

When `radio_type: sx1262_ch341` is selected:

- `sx1262` pin values are CH341 GPIO numbers `0-7`
- the adapter VID/PID is configured under `ch341:`
- host USB permissions matter more than SPI kernel overlays
- with multiple adapters, set `ch341.bus` and `ch341.address`, and/or
  `ch341.serial_number` when the adapter exposes one; VID/PID alone cannot
  distinguish identical devices. Recheck USB addresses after reconnects.

```yaml
radio_type: sx1262_ch341

ch341:
  vid: 6790
  pid: 21778

sx1262:
  cs_pin: 0
  rxen_pin: 1
  reset_pin: 2
  busy_pin: 4
  irq_pin: 6
  use_dio3_tcxo: true
  use_dio2_rf: true
```

For a common E22 mapping, the repo README uses:

| Function | CH341 GPIO |
| --- | --- |
| CS | 0 |
| RXEN | 1 |
| Reset | 2 |
| Busy | 4 |
| IRQ | 6 |

## openHop USB modem hosts

When `radio_type: modem_usb` is selected:

- the modem presents itself as a USB serial device such as `/dev/ttyACM0`
- the modem firmware handles the LoRa radio
- the repeater still owns node behavior, API, dashboard, MQTT, GPS, and identities

Minimal transport block:

```yaml
radio_type: modem_usb

modem_usb:
  port: "/dev/ttyACM0"
  baudrate: 921600
  lbt_enabled: true
  lbt_max_attempts: 5
```

## openHop TCP modem hosts

When `radio_type: modem_tcp` is selected:

- the modem runs on another board and exposes a TCP service over LAN, Wi-Fi, or Ethernet
- replace the example host before starting the service
- set the modem LAN IP or actual board-specific mDNS name under `modem_tcp.host`

Minimal transport block:

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

If you do not have RF hardware on this host at all, use `radio_type: null` and skip modem sections entirely.

## Multiple radios

A nonempty top-level `radios:` list builds an RF Fabric stack instead of the
legacy single-radio configuration. Each entry needs a unique `id`, its backend,
air settings, and hardware/transport settings. This requires Core with RF Fabric
support. See the commented multi-radio examples in the
[canonical config](https://github.com/openhop-dev/openhop_repeater/blob/dev/config.yaml.example).

- Give native radios distinct chip-select/control pins and CH341 radios distinct
  USB selectors; do not let two entries open the same hardware.
- Omitted sections inherit the top-level section. An entry's `radio`, `sx1262`,
  or transport block **replaces** that whole section rather than deep-merging
  individual fields; provide a complete block when overriding it.
- Configure `fabric.default_radio` and `fabric.tx_mode` deliberately. `default`
  uses the default radio, `sticky` uses the last receiving radio, and `bridge`
  selects another radio (intended for a two-radio backhaul, not broadcast-to-all).
- `fabric.use_fabric: true` can wrap a single radio too. Put this key under
  `fabric`, not inside the `radios` sequence.
- Back up and edit YAML deliberately, restart, and check each radio's startup.
  The legacy helper is not a multi-radio editor. To isolate software without RF,
  remove the active `radios` list from the diagnostic config as well as selecting
  top-level `radio_type: null`.

## Board-specific notes

### uConsole

- Uses SPI1 in the current preset set
- Requires its own overlay and GPS/RTC host setup

### meshadv / HT-RA62 / E22-class boards

- Often require `use_dio3_tcxo: true`
- Some also require `use_dio2_rf: true`
- Some newer presets also require `use_gpiod_backend: true` and `gpio_chip: 1`
- The current `meshadv-mini` preset explicitly enables both DIO3 TCXO control and
  DIO2 RF-switch control. Reapply the current preset or set both flags after an
  upgrade if an older config was copied forward.

### Waveshare SPI HAT

- Supported only in SPI form, not UART variants
- No longer the recommended default hardware in the upstream README

## Verifying hardware access

### Native SPI

```bash
ls /dev/spidev*
```

You should see a device such as `/dev/spidev0.0`.

### CH341

```bash
lsusb -d 1a86:5512
```

The host must expose the USB adapter with the correct permissions before the repeater can use it.

### Service logs

```bash
journalctl -u openhop-repeater -f
```

If the hardware setup is wrong, this is the first place to look.

## Radio configuration helper

The standard install directs you to browser onboarding. The optional legacy
terminal helper offers SX1262 presets (including CH341) and KISS:

```bash
sudo bash setup-radio-config.sh /etc/openhop_repeater
```

Use it to apply an SX1262/CH341 preset or write KISS serial settings. Its text
substitutions can also affect unrelated same-named keys; back up first and check
GPS/HTTP ports and board-specific fields afterward. Prefer the browser for normal
reconfiguration. After onboarding, configure `modem_usb`, `modem_tcp`, and `null`
through **System → Configuration → Radio → Radio Hardware** or by editing the
config directly, then restart Repeater.

## Related pages

- [Installation](/projects/openhop-repeater/installation/)
- [Configuration Reference](/projects/openhop-repeater/config-file/)
- [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/)
- [KISS Setup](/projects/openhop-repeater/kiss-setup/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
