---
title: KISS Modem Protocol Compatibility
description: MeshCore KISS modem framing, constants, wrapper behavior, errors, and transport boundaries in openHop Core.
sidebar:
  order: 8
---

openHop Core supports two related serial KISS integrations. Choose the wrapper
for the firmware you actually have; “KISS” alone does not imply the MeshCore
SetHardware extension API.

This compatibility guide tracks openHop Core `dev` commit
[`68272ce`](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/hardware/kiss_modem_wrapper.py)
and the pinned MeshCore protocol document at
[`fb2c61f`](https://github.com/meshcore-dev/MeshCore/blob/fb2c61f862fcd4c6e08cf0f882175ca260052b13/docs/kiss_modem_protocol.md).
That MeshCore revision includes the 255-byte MTU, single-pending-TX behavior,
`TxBusy`, non-blocking host-output queue, and `0xF8`/`0xF9` unsolicited events
implemented by the current wrapper.

## Choose the serial wrapper

| Integration | Class | What it carries |
| --- | --- | --- |
| Generic KISS TNC | `KissSerialWrapper` | Standard KISS data/configuration framing on a selected KISS port; optional device-specific CLI setup before entering KISS mode |
| MeshCore KISS modem | `KissModemWrapper` | MeshCore packets in KISS Data frames plus MeshCore cryptography, radio configuration, telemetry, status, and signal metadata in SetHardware frames |

`KissSerialWrapper` is not a substitute for `KissModemWrapper` when an
application needs modem identity or MeshCore SetHardware commands. Conversely,
a generic KISS TNC is not required to implement those MeshCore extensions.

Both wrappers are serial transports. `USBLoRaRadio` and `TCPLoRaRadio` use the
openHop Modem binary protocol (`0xAA` sync, command, little-endian length,
payload, and CRC); they are **not KISS over USB/TCP**. `WsRadio` is another
separate transport. See [Architecture and Transports](/projects/openhop-core/architecture-and-transports/).

## Serial and frame format

The pinned MeshCore modem protocol specifies 115200 baud, 8 data bits, no parity,
one stop bit, and no flow control. The wrapper defaults to 115200 baud and a
one-second caller timeout; its RX worker caps each blocking read at 0.1 seconds
so shutdown remains responsive.

```text
FEND  TYPE  DATA...  FEND
 C0    1 B  escaped    C0
```

| Name | Value | Escaping rule |
| --- | --- | --- |
| `KISS_FEND` | `0xC0` | Frame delimiter; payload `0xC0` becomes `0xDB 0xDC` |
| `KISS_FESC` | `0xDB` | Escape byte; payload `0xDB` becomes `0xDB 0xDD` |
| `KISS_TFEND` | `0xDC` | Transposed FEND |
| `KISS_TFESC` | `0xDD` | Transposed FESC |

The type byte uses port bits 7–4 and command bits 3–0. The MeshCore modem wrapper
accepts port 0. It caps a decoded frame at `MAX_FRAME_SIZE = 512`, resynchronizes
at the next FEND after an oversize or invalid escape, and limits MeshCore Data
payloads to `KISS_MAX_PACKET_SIZE = 255`. Its host `send_frame()` additionally
rejects payloads shorter than two bytes.

## Standard KISS commands

| Command | Value | openHop behavior |
| --- | --- | --- |
| Data | `0x00` | Raw MeshCore packet; one modem transmission is allowed in flight |
| TXDELAY | `0x01` | One byte, units of 10 ms |
| Persistence | `0x02` | One byte, 0–255 |
| SlotTime | `0x03` | One byte, units of 10 ms |
| TXtail | `0x04` | One byte, units of 10 ms |
| FullDuplex | `0x05` | Zero is half duplex; nonzero is full duplex |
| SetHardware | `0x06` | First data byte is the MeshCore sub-command |
| Return | `0xFF` | Protocol-defined no-op for the MeshCore modem |

`KissModemWrapper` exposes setters for persistence, slot time, TX tail, full
duplex, and signal reporting. In ordinary half-duplex mode, firmware performs
p-persistent CSMA; the wrapper's host-side listen-before-talk option defaults to
off because it would be redundant. The source reserves it for the unusual case
of a full-duplex modem attached to a physically half-duplex radio path.

## SetHardware requests and responses

Request sub-commands are `0x01` through `0x1A`:

| Range | Operations |
| --- | --- |
| `0x01`–`0x08` | Identity, random bytes, signature verify/sign, encrypt/decrypt, key exchange, SHA-256 hash |
| `0x09`–`0x10` | Set/get radio parameters and TX power, current RSSI, channel busy, airtime, noise floor |
| `0x11`–`0x18` | Version, statistics, battery, MCU temperature, sensors, device name, ping, reboot |
| `0x19`–`0x1A` | Set/get signal reporting |

Specific response codes normally use `request | 0x80`. The wrapper correlates a
single in-flight command against the expected response, an error response, and
only the explicitly accepted alternatives. Set radio, set TX power, set signal
report, and reboot may accept generic `OK (0xF0)`; set signal report also accepts
the get-form `SignalReport (0x9A)` response.

Radio parameter payloads are little-endian:

```text
frequency_hz: uint32 | bandwidth_hz: uint32 | SF: uint8 | CR: uint8
```

Runtime `configure_radio()` sends exactly those ten bytes, then sends TX power
as a separate one-byte command. The sync word is firmware-build configuration,
not part of this runtime SetRadio payload. Do not copy the wrapper's fallback
frequency, modulation, or power values as a regional preset.

Public convenience methods cover the operations above, including
`get_identity()`, `get_random()`, `sign_data()`, `verify_signature()`,
`encrypt_data()`, `decrypt_data()`, `key_exchange()`, `hash_data()`, radio/status
queries, sensor queries, and asynchronous query variants. See the exact
[`KissModemWrapper` source](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/hardware/kiss_modem_wrapper.py)
for current signatures and validation.

## Data, TxDone, and RxMeta

A host Data frame queues a raw MeshCore packet. `KissModemWrapper.send()` waits
for the unsolicited SetHardware `TxDone (0xF8)` result rather than treating a
successful UART write as successful RF transmission. Data transmission is
single-flight. The wait uses estimated LoRa airtime plus a margin, so a long
valid transmission is not limited to the flat command-response timeout.

For receive, firmware sends:

1. a Data (`0x00`) frame containing only the packet; then
2. an optional `RxMeta (0xF9)` SetHardware frame containing signed SNR×4 and
   signed RSSI dBm bytes.

The wrapper pairs those frames in arrival order. A callback may accept either
`(data)` or `(data, rssi, snr)`. If metadata does not arrive within
`RX_META_WAIT_SECONDS = 0.25`, the packet is still delivered with sentinel
metrics `-999` and `-999.0`; reception does not stall when signal reporting is
disabled. At most 64 unpaired receive frames are queued.

Call `set_event_loop()` in an asyncio application to schedule receive callbacks
through `call_soon_threadsafe()`. Without it, callbacks run in a worker executor
rather than blocking the serial RX thread.

## Errors and failure behavior

| Error | Value | Meaning |
| --- | --- | --- |
| `InvalidLength` | `0x01` | Request data is too short or has an invalid length |
| `InvalidParam` | `0x02` | Parameter is outside the accepted range |
| `NoCallback` | `0x03` | Firmware/board does not provide the feature |
| `MacFailed` | `0x04` | MAC verification failed |
| `UnknownCmd` | `0x05` | Unsupported SetHardware sub-command |
| `EncryptFailed` | `0x06` | Encryption operation failed |
| `TxBusy` | `0x07` | Another Data TX is pending or the modem's host-output queue is full |

`TxBusy` is ambiguous: it can mean pending radio TX **or** a full host-output
queue. The wrapper records it in diagnostics but does not fail an in-flight Data
send merely because it arrived. Only `TxDone` status `0x01` confirms successful
transmission; a busy indication followed by a successful `TxDone` is a successful
send. `TxBusy` is not consumed as an unrelated SetHardware command response.

No `TxDone` before the bounded deadline leaves the send unconfirmed. Neither
that timeout nor a failed `TxDone` proves that nothing went on air, so retries
must account for possible duplicate delivery. Invalid escapes and oversize
receive frames increment `frame_errors` and resynchronize.
Serial write/read failures mark the link degraded, wake waiting senders, close
the failed generation, and start guarded reconnect handling. `connect()` reports
success only after the serial reader is alive and the post-connect handshake
succeeds.

`connect()`, configuration setters, and low-level query methods commonly return
`False` or `None` for protocol/transport failure. The asynchronous LoRaRadio
`send()` raises when the modem does not report successful completion and returns
a metadata mapping on success.

## Lifecycle and compatibility checks

```python
from openhop_core.hardware import KissModemWrapper

modem = KissModemWrapper(
    "/dev/ttyUSB0",
    auto_configure=False,
)

try:
    if not modem.connect():
        raise RuntimeError("KISS modem handshake failed")
    # Configure only with settings verified for your mesh and region.
finally:
    modem.disconnect()
```

Before transmitting:

- verify the device really runs compatible MeshCore KISS modem firmware;
- ensure no other process owns the serial port;
- compare modem version/capabilities with the pinned protocol revision;
- configure frequency, bandwidth, spreading factor, coding rate, and power for
  the intended mesh and legal region;
- expect reboot and physical disconnects to drop the serial connection.

Use [Examples](/projects/openhop-core/examples/) for reviewed application flows,
[Node Usage](/projects/openhop-core/node-usage/) for dispatcher ownership, and
[API Reference](/projects/openhop-core/api-reference/#transports) for the full
transport index.
