---
title: openHop for Unraid Overview
description: Run the official openHop Repeater container through Unraid Community Applications.
sidebar:
  order: 1
---

The openHop Unraid project supplies the official Community Applications template
for openHop Repeater. It references the official Repeater images; it does not fork
or repackage the application.

## Image channels

| Channel | Image | Use |
| --- | --- | --- |
| Main | `openhop/openhop-repeater:main` | Recommended for most users |
| Dev | `openhop/openhop-repeater:dev` | Newest development updates |

Community Applications presents these as channels of one application. A direct XML
import uses Main by default and does not show the CA channel selector.

## Runtime layout

The template uses bridge networking, keeps privileged mode disabled, and publishes:

| Purpose | Container port | Default host port |
| --- | ---: | ---: |
| Web UI/API | 8000 | 8000 |
| Companion identity 1 | 5001 | 5001 |
| Companion identity 2 | 5002 | 5002 |
| Companion identity 3 | 5003 | 5003 |

Persistent mappings:

- `/etc/openhop_repeater` → `/mnt/user/appdata/openhop-repeater/config`
- `/var/lib/openhop_repeater` → `/mnt/user/appdata/openhop-repeater/data`

The template is designed primarily for an openHop TCP modem on the LAN or an
explicitly mapped USB/KISS serial device. Native SPI/GPIO is not enabled by
default.

## Start here

1. [Open openHop-Repeater in Community Applications](https://ca.unraid.net/apps/openhop-repeater-1gfdqts1upcz84)
   and follow the [installation guide](/projects/openhop-unraid/installation/).
2. [Add a USB serial device](/projects/openhop-unraid/usb-device-setup/)
3. [Complete Repeater first boot](/projects/openhop-repeater/first-boot/)

Keep the web/API and companion ports on a trusted LAN or VPN. Do not publish them
directly to the internet.

## Project links

- [Community Applications listing](https://ca.unraid.net/apps/openhop-repeater-1gfdqts1upcz84)
- [Unraid template repository](https://github.com/openhop-dev/OpenHop-Unraid-App)
- [Template issue tracker](https://github.com/openhop-dev/OpenHop-Unraid-App/issues)
- [openHop Repeater](https://github.com/openhop-dev/openhop_repeater)
