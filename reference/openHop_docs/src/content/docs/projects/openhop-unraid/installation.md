---
title: Installation and First Start
description: Install openHop Repeater from Unraid Community Applications and preserve its configuration and state.
sidebar:
  order: 2
---

## Install from Community Applications

Open the official [openHop-Repeater Community Applications listing](https://ca.unraid.net/apps/openhop-repeater-1gfdqts1upcz84),
then install it from the Unraid Apps interface:

1. Open **Apps** in the Unraid WebGUI.
2. Search for **openHop Repeater**.
3. Select Main for normal use or Dev when intentionally testing development builds.
4. Confirm the persistent paths and port mappings.
5. Apply the template and allow Unraid to create the container.

If the listing is not yet available in your CA feed, use the template repository's
current installation guidance rather than copying an unverified third-party XML.

## Check the template fields

| Setting | Default |
| --- | --- |
| Network | Bridge |
| Privileged | Disabled |
| Config | `/mnt/user/appdata/openhop-repeater/config` |
| Runtime data | `/mnt/user/appdata/openhop-repeater/data` |
| Web UI/API | Host 8000 → container 8000 |
| Companions | Host 5001–5003 → matching container ports |

The official template overrides the runtime user to root because Unraid creates new
bind-mount directories as root. It retains the image's Repeater Python site-packages
through `PYTHONPATH`. Do not remove that template contract casually.

## First start

1. Confirm ports 8000 and 5001–5003 are free, or change only the host-side values.
2. Start the container once.
3. Open `http://<unraid-ip>:8000/` and follow the first-run browser flow, or edit
   the mapped config file directly.
4. Replace the seeded example admin and guest passwords immediately.
5. Select the radio backend and verify regional frequency, power, modulation,
   antenna, and device/TCP settings before enabling transmission.
6. If companion identities are enabled, make their listeners use container ports
   5001, 5002, and 5003.

The entrypoint creates `config.yaml` on first start and conservatively merges new
defaults during later image updates while preserving configured values.

## TCP modem

A TCP modem needs no Docker device mapping. Configure `radio_type: modem_tcp` and
the modem's reachable LAN address/port in the Repeater setup flow. Confirm Unraid's
container network can reach that address.

## USB or KISS modem

Add the serial interface as a Docker **Device**, not a normal Path. Prefer a stable
`/dev/serial/by-id/...` path. See [USB Device Setup](/projects/openhop-unraid/usb-device-setup/).

## Updates and channel changes

Use Unraid's normal container update flow. Persistent config/data mappings survive
container replacement. Back them up first when the update includes schema or
identity-related changes.

To change between Main and Dev, edit the container and select the other image tag.
The openHop web UI cannot switch Docker image channels.

## Application plugins on plugin-capable images

The Unraid template keeps the official image's entrypoint; it does not launch a
separate copy of Repeater or replace startup with `python -m repeater.main`.
Current Repeater dev uses a container supervisor to start Repeater and its
application-plugin manager together. Older Main images may not contain that
subsystem: select and update the image deliberately rather than assuming channel
parity.

Keep both persistent mounts. With the normal `storage.storage_dir`, plugins live
at `/var/lib/openhop_repeater/plugins`, inside the mapped appdata `data` directory.
That includes installed releases, plugin state, data, and logs. Back up the whole
directory before changing image channels; do not assume a downgrade can consume
state written by a newer plugin or Repeater. A custom `plugins.root` must also
point into persistent storage.

No new published port or privileged mode is needed for plugin-manager IPC: it
uses a local Unix socket. `plugins.enabled: false`, or the container environment
variable `OPENHOP_PLUGIN_MANAGER=0`, disables manager startup on current dev.
Install only trusted plugins: this template runs the container as root with
access to its mounts and any explicitly mapped devices.

If the UI works but the manager is unavailable, check for `Starting plugin manager`
and manager restart errors in container logs, a disabled-manager setting, or a
custom startup override. HTTP success by itself is not plugin readiness.

Sources: [Unraid template](https://github.com/openhop-dev/OpenHop-Unraid-App/blob/d5d46dab94ca5dbb280d3f15c17f55d873956be9/templates/openhop-repeater.xml),
[Repeater dev entrypoint](https://github.com/openhop-dev/openhop_repeater/blob/ffd239dd826e2c0b3185ba8358f9a4f9cb530aba/docker-entrypoint.sh),
and [container supervisor](https://github.com/openhop-dev/openhop_repeater/blob/ffd239dd826e2c0b3185ba8358f9a4f9cb530aba/repeater/plugins/container_supervisor.py).

## Troubleshooting

```bash
docker logs --tail 100 openHop-Repeater
docker inspect openHop-Repeater
```

Common first-start failures are host-port conflicts, unwritable appdata directories,
missing USB Device mappings, or a TCP modem address unreachable from the container.
