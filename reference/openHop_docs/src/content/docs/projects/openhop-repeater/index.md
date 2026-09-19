---
title: openHop Repeater Overview
description: Operational docs for running openHop Repeater across SPI, CH341, KISS, openHop USB, and openHop TCP deployments.
sidebar:
  order: 1
---

openHop Repeater is an always-on MeshCore infrastructure node built on top of openHop Core. It can forward mesh traffic, expose a dashboard and API, run policies, host room-server and companion identities, and use radio hardware ranging from Pi HATs to USB or TCP openHop Modems.

## What this section covers

- Installation and first boot flow
- Runtime architecture and service behavior
- Hardware and radio backend options, including CH341, KISS, openHop USB, and openHop TCP
- Managed application and service plugins: catalogue installation, configuration, updates, and recovery
- Built-in sensor modules, GPS, MQTT, and companion service configuration
- openHop Modem RF, sensor, and GPS integration
- Operations, logs, and troubleshooting entry points

## Extend your Repeater

Use [Plugins](/projects/openhop-repeater/plugins/) to install and manage external
applications from the dashboard. Plugins run separately from Repeater and keep
their own dependencies and persistent data. They are trusted applications, not
sandboxed extensions.

Building an integration? [Plugin Development](/projects/openhop-repeater/plugin-development/)
covers wheel packaging, manifests, runtime configuration, and application UI assets.
Managed plugins are separate from the built-in sensor modules.

## Useful links

- Project repository: [openHop Repeater](https://github.com/openhop-dev/openhop_repeater)

## Next step

- Start with [What is openHop Repeater?](/projects/openhop-repeater/what-is-openhop-repeater/)
- Then continue to [Setup](/projects/openhop-repeater/setup/)
- Browse every topic in the [Documentation Directory](/projects/openhop-repeater/home/)
- Jump straight to [Installation](/projects/openhop-repeater/installation/), [Proxmox LXC Installation](/projects/openhop-repeater/proxmox-lxc/), [Hardware Setup](/projects/openhop-repeater/hardware-setup/), [openHop Modem](/projects/openhop-modem/), [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/), [KISS Setup](/projects/openhop-repeater/kiss-setup/), or [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
- For removal and data-retention choices, use [Uninstallation](/projects/openhop-repeater/uninstallation/)
