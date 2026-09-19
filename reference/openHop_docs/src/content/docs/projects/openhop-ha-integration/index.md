---
title: openHop Repeater Home Assistant Integration
description: Home Assistant integration docs for connecting to a local openHop Repeater instance.
sidebar:
  order: 1
---

Welcome to the docs for the `openHop Repeater` Home Assistant integration.

This integration connects Home Assistant directly to a local `openhop_repeater` instance, creates a dedicated API token during setup, and exposes repeater telemetry, MQTT broker state, control entities, and advanced service actions inside Home Assistant.

## Quick links

- [Installation](/projects/openhop-ha-integration/installation/)
- [Setup in Home Assistant](/projects/openhop-ha-integration/setup-in-home-assistant/)
- [Entities and Controls](/projects/openhop-ha-integration/entities-and-controls/)
- [Dashboard Template](/projects/openhop-ha-integration/dashboard-template/)
- [Actions and Advanced Services](/projects/openhop-ha-integration/actions-and-advanced-services/)

## Highlights

- config flow setup from the Home Assistant UI
- token-based auth after initial admin-password bootstrap
- repeater, hardware, database, MQTT, ACL, room, companion, update, and GPS telemetry
- Home Assistant sensors, binary sensors, buttons, numbers, selects, and switches
- built-in Lovelace dashboard template

## Repository

- Integration repo: [openHop HA Integration](https://github.com/openhop-dev/openHop-HA-Integration)
- openHop Repeater upstream: [openhop-dev/openhop_repeater](https://github.com/openhop-dev/openhop_repeater)
