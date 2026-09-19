---
title: Documentation Directory
description: Complete topic directory for current openHop Repeater documentation.
sidebar:
  order: 20
---

The canonical project entry point is the
[openHop Repeater Overview](/projects/openhop-repeater/). This directory provides
a longer task-oriented index without creating a second project home page.

## Start here

1. [What is openHop Repeater?](/projects/openhop-repeater/what-is-openhop-repeater/)
2. [Installation](/projects/openhop-repeater/installation/)
3. [Hardware Setup](/projects/openhop-repeater/hardware-setup/)
4. [Configuration Reference](/projects/openhop-repeater/config-file/)
5. [openHop Modem](/projects/openhop-modem/)
6. [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/)
7. [KISS Setup](/projects/openhop-repeater/kiss-setup/)
8. [Uninstallation](/projects/openhop-repeater/uninstallation/)

## Supported deployment styles

- Native SPI + GPIO hosts using `radio_type: sx1262`
- CH341 USB-SPI hosts using `radio_type: sx1262_ch341`
- Serial TNC hosts using `radio_type: kiss`
- USB serial modem hosts using `radio_type: modem_usb`
- Wi-Fi or Ethernet modem hosts using `radio_type: modem_tcp`
- Dashboard-only or companion-only hosts using `radio_type: null`
- Proxmox LXC deployments using CH341, openHop TCP, or openHop USB radios

## Current feature areas

- GPS receiver support and GPS time sync
- [managed application and service plugins](/projects/openhop-repeater/plugins/) with a catalogue, updates, logs, and persistent settings
- built-in sensor modules exposed through `/api/stats`
- openHop Modem HTTP GPS and `openhop_modem` sensor telemetry
- `mqtt_brokers` based publishing
- openHop Glass control-plane integration
- hardware presets including uConsole, meshadv, UltraPeater, and UltraPeaterZero
- neighbour link history and region/scope discovery

## Plugins

- [Install and manage plugins in the dashboard](/projects/openhop-repeater/plugins/)
- [Advanced administration and API automation](/projects/openhop-repeater/plugin-administration/)
- [Build and package a plugin](/projects/openhop-repeater/plugin-development/)
- [Plugin API and the rest of the REST contract](/projects/openhop-repeater/api-reference/)
- [Authentication and plugin trust](/projects/openhop-repeater/security-and-authentication/)

## Useful pages

- [Configuration Reference](/projects/openhop-repeater/config-file/)
- [What is openHop Repeater?](/projects/openhop-repeater/what-is-openhop-repeater/)
- [openHop Modem](/projects/openhop-modem/)
- [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/)
- [MQTT and LetsMesh Integration](/projects/openhop-repeater/letsmesh-integration/)
- [Identity Management](/projects/openhop-repeater/identity-management/)
- [Uninstallation](/projects/openhop-repeater/uninstallation/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)

## External resources

- [openHop Repeater repository](https://github.com/openhop-dev/openhop_repeater)
- [openHop Modem firmware](https://github.com/openhop-dev/openhop_modem)
- [openHop MeshCore Flasher](https://github.com/openhop-dev/openHop-Modem-Flasher)
- [openHop Core](https://github.com/openhop-dev/openhop_core)
- [MeshCore](https://github.com/meshcore-dev/MeshCore)
