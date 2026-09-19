---
title: Direct SX1262 Hardware
description: Configure SPI, GPIO, board mappings, lifecycle, and RF safety for a directly attached SX1262.
sidebar:
  order: 9
---

`SX1262Radio` drives an SX1262 directly rather than talking to a modem firmware.
It owns SPI/GPIO state, interrupt handling, receive tasks, and radio
configuration in the host process. Use it only after matching the constructor to
the exact board schematic and operating region.

This guide tracks openHop Core `dev` commit
[`77f116a`](https://github.com/openhop-dev/openhop_core/blob/77f116a8dab097642d04a16c8aaf097c0dd33cc3/src/openhop_core/hardware/sx1262_wrapper.py).
It does not define a universal pinout or radio preset.

## Supported host interfaces

The current hardware stack supports:

- Linux SPI through `SPIDevTransport`;
- Linux GPIO character devices through `python-periphery`, with an optional
  `gpiod` backend;
- a transport/GPIO override for CH341 USB-to-SPI/GPIO adapters;
- hardware chip select (`cs_pin=-1`) or a manual GPIO chip-select line.

The transport abstractions are exported from the pinned
[`hardware/transports` package](https://github.com/openhop-dev/openhop_core/tree/77f116a8dab097642d04a16c8aaf097c0dd33cc3/src/openhop_core/hardware/transports).
Direct Linux use normally opens `/dev/spidev<bus_id>.<cs_id>` and one or more
`/dev/gpiochip*` devices. CH341 pin numbers are adapter GPIO identifiers, not
Raspberry Pi GPIO numbers; do not mix the two schemes.

Install the hardware extra in a virtual environment:

```bash
python -m pip install "openhop-core[hardware]"
```

The `hardware` extra installs the default `python-periphery` GPIO path. To select
the optional `gpiod` backend with `use_gpiod_backend=True`, install both extras:

```bash
python -m pip install "openhop-core[hardware,gpiod]"
```

The default `auto` backend prefers `python-periphery` when available.

## GPIO numbering

For Raspberry Pi profiles, the configured values are BCM/GPIO line numbers, not
40-pin header positions. The default GPIO chip is `/dev/gpiochip0`.

`GPIOPinManager` also supports Linux SBC documentation that uses a global GPIO
number. For a configured number of 32 or greater, it calculates
`bank = number // 32` and `line = number % 32`; if the corresponding
`/dev/gpiochip<bank>` exists, it uses that chip and line. Otherwise it leaves the
number as a line offset on the configured chip. Verify this mapping against the
running kernel's gpiochip layout rather than assuming SoC documentation and
Linux numbering are identical.

A pin value of `-1` disables that optional host-controlled line. For chip select,
`cs_pin=-1` means use the SPI controller's hardware CS selected by `cs_id`.

## Current example board mappings

These are **profiles in the pinned `examples/common.py`**, not universal board
standards. Confirm the board revision, schematic, overlays, and physical header
before use.

| Example profile | SPI | CS | Reset | Busy | DIO1/IRQ |
| --- | --- | --- | --- | --- | --- |
| `waveshare` | bus 0, CS 0 | GPIO 21 manual | GPIO 18 | GPIO 20 | GPIO 16 |
| `uconsole` | bus 1, CS 0 | hardware CS | GPIO 25 | GPIO 24 | GPIO 26 |
| `meshadv-mini` | bus 0, CS 0 | GPIO 8 manual | GPIO 24 | GPIO 20 | GPIO 16 |

Front-end and profile-specific controls:

| Example profile | TXEN | RXEN | Special flag |
| --- | --- | --- | --- |
| `waveshare` | GPIO 13 | GPIO 12 | `is_waveshare=True` |
| `uconsole` | disabled | disabled | none in example profile |
| `meshadv-mini` | disabled | GPIO 12 | none in example profile |

Exact profile source:
[`examples/common.py`](https://github.com/openhop-dev/openhop_core/blob/77f116a8dab097642d04a16c8aaf097c0dd33cc3/examples/common.py#L266-L315).
The current Waveshare TXEN value is GPIO 13; older prose in the source docs lists
GPIO 6, so use the current executable profile plus the vendor schematic, not the
legacy prose.

Vendor/hardware references preserved from the upstream source documentation:

- [Waveshare SX1262 LoRaWAN/GNSS HAT wiki](https://www.waveshare.com/wiki/SX1262_XXXM_LoRaWAN/GNSS_HAT)
- [FrequencyLabs meshadv hardware source/profile reference](https://github.com/chrismyers2000)

Those links identify vendor/upstream material; they do not prove that every
revision uses the table above.

## Constructor wiring controls

`SX1262Radio` accepts these hardware controls:

- `bus_id`, `cs_id`, and `cs_pin` for SPI selection;
- `gpio_chip` and `use_gpiod_backend` for GPIO access;
- required radio lines `reset_pin`, `busy_pin`, and `irq_pin`;
- optional `txen_pin`, `rxen_pin`, `txled_pin`, and `rxled_pin`;
- `en_pin` or `en_pins` for board power-enable lines driven high during init;
- `is_waveshare` for the wrapper's alternate Waveshare initialization path;
- `use_dio3_tcxo` and `dio3_tcxo_voltage` for SX1262-controlled TCXO power;
- `use_dio2_rf` for SX1262 DIO2 RF-switch control.

Do not configure a host TXEN/RXEN pair and DIO2 control by guesswork. The correct
choice depends on how the module's RF switch is wired.

## TCXO, DIO2, and RF switching

### DIO3 TCXO control

When `use_dio3_tcxo=True`, initialization maps the requested voltage to an
SX1262 DIO3 output constant, calls `setDio3TcxoCtrl()`, and allows the oscillator
to stabilize. Supported map points in the wrapper are 1.6, 1.7, 1.8, 2.2, 2.4,
2.7, 3.0, and 3.3 V. A value not exactly in the map is rounded to the nearest
entry; that convenience is **not** electrical validation. Use only the voltage
required by the module datasheet.

### DIO2 RF-switch control

Initialization always calls the low-level DIO2 RF-switch configuration with the
`use_dio2_rf` boolean. Enable it only if DIO2 is wired to the module's RF switch.
Some boards expose separate host-controlled TXEN/RXEN lines instead; others do
not expose DIO2 at all.

### Host-controlled front end

When configured, TXEN/RXEN outputs are created low and switched around radio
state transitions. Optional EN pins are driven high during initialization.
Incorrect polarity or simultaneous front-end states can prevent reception or
damage an RF path; verify the schematic rather than inferring behavior from a
similarly named board.

## Permissions and device ownership

The process needs read/write access to both SPI and GPIO character devices.
Prefer device groups and udev rules over running the application as root.
Typical checks include:

```bash
stat /dev/spidev0.0
stat /dev/gpiochip0
```

On distributions that provide `spi` and `gpio` groups, add the service account
to the applicable group and start a new login/session before retrying. Group
names and udev ownership vary by distribution, so inspect the device ownership
first. Also enable the intended SPI controller/overlay and confirm the expected
`/dev/spidev*` node exists.

The GPIO manager treats “permission denied” and “resource busy” as fatal setup
errors. A busy line usually means another process or driver already owns it.
Do not launch a second radio process against the same SPI/GPIO lines: the wrapper
does not arbitrate shared physical lines for you. Multiple `SX1262Radio` instances
can coexist when each owns distinct GPIO/SPI resources. Each instance cleans up
only its own resources.

Multiple CH341 adapters can be selected by bus/address or serial number. When
more than one matching adapter is connected, an unqualified selection fails
rather than silently choosing one.

## Safe lifecycle

Construction records configuration and creates/selects the GPIO manager.
`begin()` performs hardware setup and returns `True` on success. It configures
interrupts, CS/reset/busy lines, optional front-end and LED lines, TCXO/RF-switch
behavior, calibration, modulation, TX power, and continuous receive state.
Run it only after all wiring and RF settings are verified.

```python
from openhop_core.hardware import SX1262Radio

radio = SX1262Radio(
    # Supply a board-verified SPI/GPIO mapping.
    # Supply region- and mesh-verified radio parameters.
)

try:
    if not radio.begin():
        raise RuntimeError("SX1262 initialization failed")
    # Pass radio to MeshNode or CompanionRadio here.
finally:
    radio.cleanup()
```

`cleanup()` marks shutdown, cancels the receive IRQ task, puts the radio to sleep
when possible, and releases that instance's managed GPIO lines.
`MeshNode.stop()` does not replace this cleanup; the application still
owns the radio. See [Quick Start](/projects/openhop-core/quick-start/) and
[Node Usage](/projects/openhop-core/node-usage/).

`set_rx_callback()` should be called from the application's running asyncio loop
when interrupt-backed receive delivery is required. The GPIO edge callback uses
`call_soon_threadsafe()` to hand work to that loop. The wrapper serializes TX and
RX-sensitive operations with asyncio locks and exposes `perform_cad()` for
channel-activity detection.

## Antenna, frequency, region, and TX safety

Before `begin()` or any send:

1. Attach a 50 Ω antenna/feed path intended for the configured band. Never
   transmit into an open connector or the wrong antenna path.
2. Verify the module variant and its supported frequency range.
3. Select frequency, bandwidth, spreading factor, coding rate, preamble, and
   sync word to match the intended mesh.
4. Apply local frequency allocation, duty-cycle, channel-access, and conducted
   or radiated power limits.
5. Account for antenna gain, feed-line loss, amplifier/front-end limits, and
   board thermal/current constraints.
6. Start at a conservative legal power and verify receive/transmit behavior with
   appropriate RF test equipment or a known-good peer.

The wrapper's SX1262 class limit is 22 dBm and the vendored low-level driver
clamps requests above that value, but the chip limit is not permission to
transmit at 22 dBm. Board, antenna, and regional limits can be lower. Runtime
setters such as `set_frequency()` and `set_tx_power()` do not perform regulatory
policy enforcement.

## Vendored LoRaRF provenance

The low-level `hardware/lora/LoRaRF` code is vendored and modified inside
openHop Core; it is not merely an unmodified runtime dependency. The pinned
vendored README identifies
[Chandra Wijaya Sentosa's LoRaRF-Python](https://github.com/chandrawi/LoRaRF-Python)
and links its [upstream wiki](https://github.com/chandrawi/LoRaRF-Python/wiki).
The vendored tree carries its own
[MIT license and 2022 copyright notice](https://github.com/openhop-dev/openhop_core/blob/77f116a8dab097642d04a16c8aaf097c0dd33cc3/src/openhop_core/hardware/lora/LICENSE).

No upstream LoRaRF commit identifier is recorded in the pinned vendored README
or license. Do not claim exact source parity with LoRaRF-Python `main`, and do
not replace the vendored code based only on a package version. Review openHop's
local changes and hardware tests first, including the pinned
[SX1262 TX-power mapping tests](https://github.com/openhop-dev/openhop_core/blob/77f116a8dab097642d04a16c8aaf097c0dd33cc3/tests/hardware/test_sx126x_tx_power.py).

## Related guides

- [Architecture and Transports](/projects/openhop-core/architecture-and-transports/)
- [Examples](/projects/openhop-core/examples/)
- [API Reference](/projects/openhop-core/api-reference/#transports)
- [KISS Modem Protocol](/projects/openhop-core/kiss-modem-protocol/)
