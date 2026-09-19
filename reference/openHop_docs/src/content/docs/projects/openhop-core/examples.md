---
title: Examples and Hardware Safety
description: Inventory current openHop Core examples, their side effects, and the checks required before running them.
sidebar:
  order: 6
---

The tracked examples are executable hardware programs, not unit tests. Most open a
radio, join a mesh, receive traffic, transmit RF, or send captured packets to another
host. Read the whole script and its selected transport before running it.

This inventory tracks openHop Core `dev` commit
[`77f116a`](https://github.com/openhop-dev/openhop_core/tree/77f116a8dab097642d04a16c8aaf097c0dd33cc3/examples).

## Safe verification before hardware

Verify the package and imports without opening a device:

```bash
python -c "import openhop_core; print(openhop_core.__version__)"
python -m pytest --tb=short -v
```

The repository test suite uses mocks for normal automated verification. Do not use an
example as a smoke test merely because it starts successfully.

Before any example that creates a radio:

1. Attach the correct antenna for the configured band.
2. Confirm the board revision, transport, device path, SPI/GPIO mapping, TCXO, and
   RF-switch wiring.
3. Confirm frequency, bandwidth, spreading factor, coding rate, preamble, sync word,
   and TX power against the intended mesh and local regulations.
4. Stop other programs that own the same serial, SPI, or GPIO resources.
5. Know whether the example transmits, listens, changes radio state, or exports data.

## Current example inventory

| Script | Purpose | Important side effects |
| --- | --- | --- |
| `send_tracked_advert.py` | Sends repeated tracked adverts and counts observed repeats | Opens hardware and transmits RF repeatedly |
| `send_flood_advert.py` | Sends a flood advertisement | Opens hardware and transmits RF |
| `send_direct_advert.py` | Sends a direct advertisement | Opens hardware and transmits RF; requires a valid destination/path context |
| `send_text_message.py` | Sends a direct text message | Opens hardware, transmits RF, and requires a real contact/destination |
| `send_channel_message.py` | Sends a channel message | Opens hardware and transmits RF using channel material in the script/configuration |
| `ping_repeater_trace.py` | Sends a trace request and waits for path information | Opens hardware and transmits diagnostic traffic |
| `discover_nodes.py` | Sends discovery traffic and collects matching nodes | Opens hardware and transmits RF |
| `respond_to_discovery.py` | Listens and responds to discovery requests | Opens hardware, receives traffic, and can transmit responses |
| `calibrate_cad.py` | Sweeps and validates CAD parameters | Reconfigures a live SX1262 and repeatedly performs channel-activity detection; use on known hardware in a controlled RF environment |
| `wireshark_stream.py` | Streams observed packet bytes to Wireshark over UDP | Opens hardware, receives mesh traffic, and exports captures to a configured network host |
| `login_server.py` | Demonstrates repeater-style login and permissions | Opens hardware, receives/transmits RF, and contains deterministic example credentials that are unsafe outside isolated testing |
| `common.py` | Shared transport/node factory and output helpers | Importing is passive, but calling `create_radio()` opens/configures the selected device |

`examples/__init__.py` only marks the directory as a package.

## Transport selection

The current shared factory supports several radio names. Inspect
[`examples/common.py`](https://github.com/openhop-dev/openhop_core/blob/77f116a8dab097642d04a16c8aaf097c0dd33cc3/examples/common.py)
before relying on a name because each path has different arguments and side effects.

Current families include:

- direct SX1262 profiles such as Waveshare, uConsole, and meshadv-mini;
- CH341 USB-to-SPI/GPIO;
- generic serial KISS;
- MeshCore KISS modem;
- openHop Modem through the canonical `modem_usb` or `modem_tcp` choices.

Use [Direct SX1262 Hardware](/projects/openhop-core/direct-sx1262-hardware/) for
current board mappings and
[KISS Modem Protocol Compatibility](/projects/openhop-core/kiss-modem-protocol/) for
the distinction between generic KISS and MeshCore modem extensions.

## Shared factory behavior

`create_radio()` selects and initializes a concrete transport. Depending on the
selection, it can:

- open `/dev/spidev*` and `/dev/gpiochip*`;
- claim CH341 adapter pins;
- open a serial device;
- connect to a TCP modem;
- configure radio modulation and transmit power;
- start receive callbacks or worker threads.

`create_mesh_node()` calls the radio factory and returns a node around it. The caller
still owns node shutdown and radio cleanup.

The example profiles are executable configuration, but they are not universal
hardware standards. Validate every value against the exact board schematic.

## Message and advert examples

Advert, direct-message, channel-message, discovery, and trace examples all generate
mesh packets. Before running one:

- replace any placeholder destination or channel material;
- check that the identity is disposable or intentionally persisted;
- verify the packet type and route against current source;
- avoid repeated flood traffic on a production mesh;
- use conservative legal TX settings.

For application code, prefer higher-level companion methods over copying packet
construction snippets from old MkDocs pages. See
[Companion Applications](/projects/openhop-core/companion-applications/) and
[Node Usage](/projects/openhop-core/node-usage/).

## CAD calibration

`calibrate_cad.py` performs a staged search over detection peak/minimum settings and
validates candidates. It is hardware-specific diagnostic work, not a generic startup
step.

Run it only when:

- the SX1262 and antenna path are known-good;
- the radio configuration matches the target mesh;
- the local RF environment is understood;
- no other process owns the device;
- changing CAD parameters is acceptable.

A result from one board, modulation, or RF environment is not automatically valid on
another deployment.

## Discovery responder and login server

`respond_to_discovery.py` and `login_server.py` accept inbound mesh traffic and can
transmit responses. They should not be exposed unattended.

The login server contains hardcoded deterministic demonstration credentials. Treat
them as public test data. Never reuse them for a real identity, password, ACL, or
service. Build production authentication around protected application-owned state,
rate limits, and explicit permissions.

## Wireshark streaming

`wireshark_stream.py` sends captured packet data over UDP to the requested IP and
port. This crosses a network trust boundary and may expose identifiers, routing
information, and payload bytes.

Use an isolated capture network, restrict the destination, and follow local policy
for mesh traffic. UDP provides no confidentiality, authentication, or delivery
guarantee.

## Cleanup

Every hardware example should stop the node and close the concrete transport in a
`finally` path. If a script exits badly:

1. confirm no Python process still owns the device;
2. verify SPI/GPIO/serial resources were released;
3. power-cycle only when the board procedure permits it;
4. inspect logs before rerunning;
5. do not start a second copy against busy hardware.

## Source and migration note

The legacy `docs/docs/examples.md` and `examples/README.md` contained useful topic
inventories but also duplicated old pin, dependency, and command guidance. This page
uses the current tracked scripts and transport implementations as authority rather
than copying those files verbatim.

## Related guides

- [Quick Start](/projects/openhop-core/quick-start/)
- [Node Usage](/projects/openhop-core/node-usage/)
- [Architecture and Transports](/projects/openhop-core/architecture-and-transports/)
- [API Reference](/projects/openhop-core/api-reference/)
- [Core Development](/projects/openhop-core/development/)
