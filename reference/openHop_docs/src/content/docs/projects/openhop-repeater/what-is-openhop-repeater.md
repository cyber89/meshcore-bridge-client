---
title: What is openHop Repeater?
description: A first-user overview of what openHop Repeater does for MeshCore networks, supported hardware paths, policies, room servers, companions, and modem options.
sidebar:
  order: 2
---

openHop Repeater is an always-on MeshCore node that runs on a Linux host, usually a Raspberry Pi or small single-board computer, or in Docker on any host that can reach the selected radio/modem device. It listens for LoRa MeshCore traffic, forwards packets for the mesh, and provides a web dashboard and API for configuring and monitoring the node.

The main use case is separating the always-on Repeater service from the radio placement problem. Put the radio where it works best, then run Repeater wherever it is easiest to power, manage, and network.

For example:

- Put a Wi-Fi Heltec V4 modem in a window for better RF placement, then run Repeater in Docker on another machine indoors and connect to the modem over TCP.
- Put a wired Ethernet modem near an antenna and run Repeater somewhere else on the LAN.
- Build an outdoor box with a Luckfox or similar small Linux board plus an SPI LoRa radio for a self-contained deployment.
- Run Repeater on a Raspberry Pi with a LoRa HAT when the Pi and antenna can live in the same place.
- Plug a USB modem into a mini PC, NAS, Home Assistant host, or other always-on machine and run Repeater there.
- Run it as a monitoring or observer node that listens continuously and uploads mesh activity, packet history, and node health to MQTT without needing to be a handheld client.

## What it does for a MeshCore network

A basic Repeater can:

- receive and forward MeshCore LoRa packets
- advertise itself as a repeater node
- apply radio settings for your local mesh, such as frequency, bandwidth, spreading factor, and coding rate
- expose a web dashboard and REST API
- keep packet history and diagnostics
- publish telemetry to MQTT
- report system, sensor, modem, and GPS status
- act as a monitoring or observer node that uploads packet activity and mesh health to MQTT
- run as a systemd service for unattended operation

## More than packet forwarding

openHop Repeater can also host higher-level MeshCore services.

### Application and service plugins

The plugin manager installs external applications from a catalogue or a local
Python wheel. A plugin can provide a dashboard application, a background service,
or both. It has versioned code, its own Python environment when needed, and
persistent data that survives updates.

Manage installation, configuration, enable/disable state, logs, and updates from
the Plugins page. These applications run outside the Repeater process, but they
are not sandboxed: install only code and dependencies you trust. This system is
separate from the built-in sensor modules that collect host telemetry.

See [Plugins](/projects/openhop-repeater/plugins/) for the operator guide and
[Plugin Development](/projects/openhop-repeater/plugin-development/) for packaging.

### Runtime policies

Policies let the Repeater enforce network behavior instead of blindly forwarding everything. A policy can allow or drop matching traffic as the mesh grows.

Use this when you want a fixed node to have predictable rules for traffic handling rather than relying only on client-side behavior.

### Room server

A room server identity lets the Repeater host a persistent room-style MeshCore service. The room server has its own identity and settings, so it can operate as a logical node managed by the same Repeater process.

Use this when you want a fixed, always-available mesh endpoint for shared communication.

### Companion identity

A companion identity exposes the MeshCore frame protocol over TCP for client software. Each companion has its own node name, identity, TCP port, bind address, and timeout settings.

Use this when another app or service should connect to the Repeater as a MeshCore companion without directly owning the radio hardware.

## Hardware choices

openHop Repeater is not tied to one radio carrier. You choose a radio backend in `config.yaml` with `radio_type`.

| Hardware path | `radio_type` | Use when |
| --- | --- | --- |
| Pi HAT or local SPI SX1262 | `sx1262` | The radio is wired directly to the Linux host over SPI and GPIO. |
| CH341 USB-SPI SX1262 adapter | `sx1262_ch341` | The SX1262 is reached through a CH341 USB-SPI adapter. |
| Serial KISS TNC | `kiss` | You already have a KISS-compatible modem or TNC. |
| openHop Modem over USB | `modem_usb` | A flashed ESP/nRF modem board is plugged into the Repeater host over USB serial. |
| openHop Modem over LAN | `modem_tcp` | A flashed ESP modem board is on Wi-Fi or Ethernet and exposes the modem TCP service. |
| No RF hardware | `null` or `none` | You only need dashboard, API, room-server, companion, or development behavior. |

This means you can run the same Repeater software with a Pi radio HAT, an outdoor SPI radio box, a USB-connected modem, or a Wi-Fi/Ethernet modem located somewhere else on the LAN.

When using Docker, the host does not have to be a Pi as long as the container can access what it needs: a mapped USB device, a mapped SPI/GPIO device, or a reachable TCP modem. This is especially useful for running Repeater on a NAS, mini PC, Proxmox/LXC-style host, Home Assistant host, or other always-on machine while the radio hardware sits on USB or elsewhere on the network.

## Using openHop Modem hardware

openHop Modem firmware turns supported ESP32-family and nRF52 LoRa boards into modem devices. The modem owns the low-level radio hardware, while Repeater still owns MeshCore routing, identities, policies, room servers, companions, history, dashboard, and API.

The typical modem flow is:

1. Choose a supported modem board.
2. Flash it from the browser at [flasher.openhop.dev](https://flasher.openhop.dev/).
3. Connect it to Repeater over USB, Wi-Fi, or Ethernet.
4. Select `radio_type: modem_usb` or `radio_type: modem_tcp` in Repeater.
5. Optionally enable modem HTTP telemetry as a Repeater sensor.
6. Optionally use modem HTTP GPS as Repeater's native GPS source.

See [openHop Modem](/projects/openhop-modem/) for the device and flasher docs.

## Sensors and GPS

Repeater can collect diagnostics from the host and from optional sensors. Sensor data appears under `/api/stats` and can be shown by dashboards or integrations.

A GPS source is separate from generic sensor telemetry. If GPS is enabled, Repeater can expose a native `/api/gps` endpoint, show GPS diagnostics, and optionally use a valid fix in outgoing adverts.

For modem deployments, keep these concepts separate:

- `radio_type: modem_usb` or `modem_tcp` selects the RF transport.
- `type: openhop_modem` adds modem diagnostics to `/api/stats -> sensors`.
- `gps.source: modem_http` makes the modem's GPS payload Repeater's native GPS source.

## When to use Repeater

Use openHop Repeater when you want a fixed MeshCore node that can stay online, forward traffic, and provide services even when mobile clients are offline.

Common deployments include:

- a Raspberry Pi with an SX1262 HAT in a good RF location
- an outdoor Luckfox-style Linux box with an SPI LoRa radio and weatherproof enclosure
- a small Linux host with a USB modem board
- a Docker deployment on an always-on host with USB, SPI/GPIO, or TCP modem access
- a Repeater host indoors connected to a Wi-Fi modem in a window
- a Repeater host indoors connected to an outdoor wired modem over Ethernet
- a monitoring or observer node that uploads packet activity and mesh health to MQTT
- a dashboard/API-only host for development or companion services
- a room-server or policy-managed infrastructure node

## Where to go next

- [Setup](/projects/openhop-repeater/setup/) for the install flow.
- [Hardware Setup](/projects/openhop-repeater/hardware-setup/) for direct radio hardware.
- [openHop Modem](/projects/openhop-modem/) for flashing ESP/nRF modem devices.
- [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/) for modem radio config.
- [Configuration Reference](/projects/openhop-repeater/config-file/) for commonly used settings and schema guidance.
