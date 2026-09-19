---
title: openHop HA Add-on Overview
description: Run openHop Repeater inside Home Assistant using the openHop HA Add-on repository.
sidebar:
  order: 1
---

openHop HA Add-on packages `openhop_repeater` as Home Assistant add-ons so you can run the repeater inside Home Assistant with the same upstream config model and web UI.

## What this section covers

- repository and channel overview
- installation flow inside Home Assistant
- where the add-on stores `config.yaml` and runtime state
- host-access expectations for GPIO, SPI, USB, serial, and network transports

## Useful links

- Project repository: [openHop HA Add-on](https://github.com/openhop-dev/openHop-HA-Add-on)
- Upstream repeater: [openHop Repeater](https://github.com/openhop-dev/openhop_repeater)

## Channels

- `openHop Repeater Dev` tracks `openhop/openhop-repeater:dev`
- `openHop Repeater Main` tracks `openhop/openhop-repeater:main`

These are separate add-ons, not a runtime channel selector. Each has its own slug,
private config mount, identity, and persistent data. Installing one does not move
or copy state from the other.

## Next step

- Start with [Installation](/projects/openhop-ha-addon/installation/)
- Then read [Configuration](/projects/openhop-ha-addon/configuration/)
- Use [Host Access and Storage](/projects/openhop-ha-addon/host-access/) for GPIO, SPI, USB, and path details
