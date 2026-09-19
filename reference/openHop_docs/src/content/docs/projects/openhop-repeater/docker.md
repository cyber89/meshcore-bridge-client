---
title: Docker Deployment
description: Run openHop Repeater with persistent storage and USB, TCP, SPI, or no-radio backends.
sidebar:
  order: 4.5
---

## Choose an image

The published container tags follow the Repeater branches:

- `openhop/openhop-repeater:main` for the stable line
- `openhop/openhop-repeater:dev` for development testing

Pin a release or digest when reproducibility matters. Upgrading a container means
pulling the new image and recreating the container while retaining its volumes.

Current development images include the default RepeaterUI, **not** the old bundled
openHop Console. Before upgrading an older image with
`web.web_path: /opt/pymc_console/web/html`, switch back to the default RepeaterUI.
Install optional Console functionality through the plugin catalogue instead.

## Persistent paths

Persist both runtime paths:

| Container path | Purpose |
| --- | --- |
| `/etc/openhop_repeater` | Configuration and identity material |
| `/var/lib/openhop_repeater` | SQLite, RRD, backups, plugin releases/settings/data/logs, and other state |

Use named volumes or host directories. Do not bind-mount only a single
`config.yaml` into an otherwise ephemeral `/etc/openhop_repeater`; startup may need
to create an identity and other files beside it.

The published image runs unprivileged as UID/GID `15888:15888`. Ensure host bind
mounts are writable by that identity before startup. `PUID`/`PGID` are image build
arguments, not a runtime entrypoint that changes ownership when set in `.env`.

Plugin releases retain wheels and isolated venvs under the data volume. Keep those
wheels: the manager can rebuild venvs after a Python minor-version change. Rebuilds
may need network access and compatible dependencies; older releases without a
retained wheel require reinstallation. Architecture or absolute path changes are
not covered by this rebuild detection. If `plugins.root` is outside the mounted
data directory, provide its own persistent writable mount and backup.

## Compose example

This minimal example has no hardware mappings and uses the development image.
For the repository's full `docker-compose.yml`, copy `.env.example` to `.env`,
select `OPENHOP_REPEATER_IMAGE`, and remove nonexistent/unneeded SPI, GPIO, and USB
bus mappings before starting. Device access must match the host; `.env` group
IDs can be obtained with `getent group dialout`, `getent group gpio`, and
`getent group spi` where those groups exist.

```yaml
services:
  repeater:
    image: openhop/openhop-repeater:dev
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - repeater_config:/etc/openhop_repeater
      - repeater_data:/var/lib/openhop_repeater

volumes:
  repeater_config:
  repeater_data:
```

Open `http://<docker-host>:8000/setup` after first startup.

The commands below use the example's service name `repeater`; the repository
Compose service is named `openhop-repeater`. Use that name when operating the
shipped file. Custom named volumes must also be declared under top-level
`volumes:`; use `external: true` only when intentionally attaching existing volumes.

## Radio access

- **TCP modem:** requires no device mapping; configure `radio_type: modem_tcp` and
  make sure the container can reach the modem host and port.
- **No radio:** use `radio_type: null` for UI/API evaluation without RF I/O.
- **USB modem or KISS:** map the host serial device, for example
  `/dev/ttyACM0:/dev/ttyACM0`. Host udev rules and permissions control the device;
  udev does not run inside the container.
- **CH341:** map the required host USB bus/device and give the runtime account
  permission to use it. Native SPI mappings do not grant CH341 access.
- **SPI/GPIO:** map only the required SPI/GPIO devices. Board-specific GPIO access
  may require additional host groups or devices; avoid broad `privileged: true`
  unless the hardware path genuinely requires it and you understand the exposure.

Never start an RF backend without the correct antenna and validated regional radio
settings.

### USB serial device names

Prefer a stable host name, but do not place colon-containing ESP32-S3
`/dev/serial/by-id/` paths in Docker's `host:container[:permissions]` device
syntax. By-path names can contain colons too. For a matching board, install
`99-openhop-modem.rules` from a reviewed openHop Core checkout on the **host**:

```bash
sudo cp 99-openhop-modem.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty --action=change
```

The rule provides `/dev/openhop-modem` for USB ID `303a:1001`. With multiple
matching devices, restrict it to the intended serial number. Confirm the symlink
exists, then add this under the Compose service and set `kiss.port` or
`modem_usb.port` to the same container-side path:

```yaml
devices:
  - /dev/openhop-modem:/dev/openhop-modem
```

The optional read-only `/dev:/host/dev:ro` mount lets setup discover host device
names; it does **not** grant access. The selected device still needs a `devices:`
entry. Recreate the container after changing device mappings and recheck access
after unplugging/reconnecting a modem.

## Plugin manager

The image runs Repeater and the plugin manager under a process supervisor and
`tini`; do not install or invoke systemd inside it. The supervisor forwards stop
signals to both services and plugin process groups, and restarts the manager if
it exits while Repeater stays running.

The manager is enabled by default. To opt out, set `plugins.enabled: false` in
config, or add the following explicitly under the Compose service, then recreate
the container:

```yaml
environment:
  OPENHOP_PLUGIN_MANAGER: "0"
```

Putting this variable only in `.env` does not pass it into the shipped Compose
service. Repeater remains usable without the manager, but plugin operations are
unavailable. Plugins are trusted applications, **not sandboxed**; their separate
venvs isolate dependencies, not host access or credentials.

## Operations

```bash
docker compose logs -f repeater
docker compose pull
docker compose up -d
```

For a local source image, update the intended checkout and stage the matching
verified RepeaterUI assets before rebuilding:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

The Dockerfile packages the frontend in its build context; it does not fetch/build
RepeaterUI. Pulling Git changes or restarting a container does not rebuild an image.

At startup, user config overrides the current image's bundled defaults during
merge. A previous `config.yaml.example` in the persistent volume is preserved,
but is not the upgrade merge source. If config is unwritable, a temporary merged
fallback can be used for that startup only; fix ownership and keep
`storage.storage_dir` absolute and inside the persistent mount.

Back up both persistent volumes before upgrades or identity changes. Keep port 8000
on a trusted LAN/VPN or place it behind an authenticated reverse proxy.

Verify container logs, dashboard access, expected radio connection, and enabled
plugin status after recreation. Do not use the dashboard's native updater or
`docker compose down -v` for image upgrades.

## Related pages

- [First Boot](/projects/openhop-repeater/first-boot/)
- [Hardware Setup](/projects/openhop-repeater/hardware-setup/)
- [Security and Authentication](/projects/openhop-repeater/security-and-authentication/)
