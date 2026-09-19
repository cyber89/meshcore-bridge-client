---
title: Configuration
description: Where the add-on stores config.yaml and how it maps to the upstream openHop Repeater schema.
sidebar:
  order: 3
---

The add-on uses a real repeater config file at:

```text
/config/config.yaml
```

Inside the container, `/config` is the add-on's private config mount. On the host, that data lives under the add-on's `addon_config` directory rather than Home Assistant's main `/config` folder.

Current location notes shipped by the add-ons:

- dev channel: `addon_config/*_openhop_repeater_dev/config.yaml`
- main channel: `addon_config/*_openhop_repeater_main/config.yaml`

The wildcard prefix is assigned by Home Assistant. Use the config-location note
shown in the installed add-on rather than guessing the full host path.

## First-start behavior

On first start, the add-on bootstrap helper creates:

- `/config/config.yaml`
- `/config/identity.key` when openHop Repeater generates a node identity
- `/var/lib/openhop_repeater` for runtime state

The helper atomically replaces the template's shared admin password, guest
password, and JWT secret with unique generated values. On later image updates it
merges missing template defaults while preserving configured values, custom
settings, passwords, and secrets. Invalid YAML stops startup instead of being
silently replaced.

Inside the container, `/etc/openhop_repeater` is a symlink to `/config`, so the
upstream runtime still opens `/etc/openhop_repeater/config.yaml`. If the Repeater
updates the config through its supported manager/API, those changes persist.

The Dev and Main add-ons have distinct private mounts. Configuration and identity
do not migrate automatically between their slugs.

## Minimum fields to review

At minimum, review:

- `repeater.node_name`
- `repeater.security.admin_password`
- `repeater.security.guest_password`
- `radio_type`
- `radio.frequency`

If you are using direct SX1262 hardware, also review the `sx1262` block. If you are using modem-style transports, review `kiss`, `modem_usb`, or `modem_tcp` instead.

## Supported upstream backends

The add-on follows the upstream repeater schema, including:

- `sx1262`
- `sx1262_ch341`
- `kiss`
- `modem_usb`
- `modem_tcp`
- `null`

For the full schema, use the main [openHop Repeater Configuration Reference](/projects/openhop-repeater/config-file/).

## Example: openHop TCP inside the add-on

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

The add-on does not invent a second config model. It passes the normal Repeater
schema through. The setup route is only for initial onboarding; after that use
**System → Configuration → Radio → Radio Hardware** or edit the file and restart.
Initial onboarding is available at:

```text
http://<home-assistant-host>:8000/setup
```

Protect the private add-on config: it may contain identity keys, passwords, JWT
secrets, MQTT credentials, and modem tokens.

## Related pages

- [Host Access and Storage](/projects/openhop-ha-addon/host-access/)
- [openHop Repeater Configuration Reference](/projects/openhop-repeater/config-file/)
- [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/)
