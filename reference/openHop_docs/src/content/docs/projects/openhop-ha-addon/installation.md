---
title: Installation
description: Install the openHop HA Add-on repository and choose the right add-on channel.
sidebar:
  order: 2
---

The add-on repository lives at:

```text
https://github.com/openhop-dev/openHop-HA-Add-on
```

## Choose a channel

- `openHop Repeater Dev` follows the upstream `:dev` image
- `openHop Repeater Main` follows the upstream `:main` image

If you want the newest Repeater features first, use Dev. Use Main for the
mainline channel. They are separate installed add-ons with separate slugs and
storage; switching means a manual migration of config, identity, and state rather
than changing a channel setting.

## Add the repository

Add the repository URL to Home Assistant's add-on repositories list, then refresh the store.

## Install the add-on

1. Install either `openHop Repeater Dev` or `openHop Repeater Main`.
2. Review the add-on's broad hardware privileges. If Home Assistant exposes a
   Protection mode control, local GPIO/SPI/USB access may require it to be off.
3. Start the add-on once. First start creates the complete `/config/config.yaml`
   and replaces the template's shared admin password, guest password, and JWT
   secret with unique values.
4. Stop the add-on before editing hardware settings.
5. Open the private `config.yaml`, record the generated admin/guest credentials,
   and configure the radio backend and regional settings.
6. Start the add-on again, then open `http://<home-assistant-host>:8000`.
7. Restart the add-on after later changes that require a Repeater restart.

## Web UI

The add-on exposes the upstream repeater UI on:

```text
http://<home-assistant-host>:8000
```

The add-on uses host networking, so the dashboard and any companion/room-server
listeners bind directly on the Home Assistant host. Avoid running both channels
at the same time unless every listener port is deliberately separated.

## Plugin-manager startup and upgrades

The current upstream add-on wrapper launches
`repeater.plugins.container_supervisor` when that module exists in the packaged
Repeater image. The supervisor starts both Repeater and its separate application
plugin manager, restarts a failed manager while Repeater remains running, and
forwards shutdown signals to both process groups. The add-on's outer wrapper
preserves bounded clean-restart handling.

Older channel images without the supervisor module fall back to `repeater.main`.
An installed supervisor failing to start is an error, not a reason to silently
disable plugin support. Main and Dev can contain different Repeater capabilities.

If the dashboard loads but reports **plugin manager unavailable** after an
upgrade:

1. Update the Home Assistant add-on itself, not just Repeater code inside it.
   Older wrappers launched only `repeater.main` and bypassed the image's plugin
   manager startup.
2. Check the add-on log for
   `using runtime repeater.plugins.container_supervisor` and
   `Starting plugin manager`. A web page loading alone does not prove plugin IPC
   is available.
3. Check whether `plugins.enabled: false` intentionally disables the manager.
4. Confirm the runtime data path is persistent and writable; see
   [Host Access and Storage](/projects/openhop-ha-addon/host-access/).

This behavior is source-verified in the upstream wrapper at
[`5fad1c0`](https://github.com/openhop-dev/openHop-HA-Add-on/blob/5fad1c09d6881d036093c72f716c9d2fab54d36b/openhop_repeater_dev/run.sh)
(shared by both channels) and Repeater dev's
[`container supervisor`](https://github.com/openhop-dev/openhop_repeater/blob/ffd239dd826e2c0b3185ba8358f9a4f9cb530aba/repeater/plugins/container_supervisor.py).
Mutable image tags and installed add-on versions must still be checked separately.

## Backups and channel changes

Both manifests request cold Home Assistant backups. Before uninstalling, changing
channels, or repairing a failed startup, create a backup and confirm it includes
the add-on's private config and data. Never copy only `config.yaml`: identity,
policy, messages, contacts, and other runtime state may live in the add-on data.

## Architectures

The current add-on manifests declare:

- `aarch64`
- `amd64`

## Related pages

- [Configuration](/projects/openhop-ha-addon/configuration/)
- [Host Access and Storage](/projects/openhop-ha-addon/host-access/)
- [openHop Repeater Configuration Reference](/projects/openhop-repeater/config-file/)
