---
title: Troubleshooting
description: Diagnose service, configuration, radio, modem, dashboard, and storage problems safely.
sidebar:
  order: 17
---

Start with logs and preserve the first error. Avoid changing radio, permissions,
packages, and config simultaneously; that hides the root cause.

## Quick diagnostics

```bash
sudo systemctl status openhop-repeater
sudo journalctl -u openhop-repeater -n 100 --no-pager
sudo journalctl -u openhop-repeater -f
```

The current native install uses:

- application: `/opt/openhop_repeater`;
- config: `/etc/openhop_repeater/config.yaml`;
- state: `/var/lib/openhop_repeater`;
- service: `openhop-repeater`.

Do not paste the full config into a support request. It can contain passwords,
tokens, location, MQTT credentials, and private identity material. Redact secrets
and include only the relevant section plus the error.

## Service does not start

Read the earliest traceback or error after a restart:

```bash
sudo systemctl restart openhop-repeater
sudo journalctl -u openhop-repeater -n 150 --no-pager
```

Common causes:

- invalid YAML or a key at the wrong indentation;
- wrong `radio_type` for the configured backend block;
- missing serial, SPI, GPIO, or USB device;
- service-user permission to the selected device;
- another process already using the device or TCP port;
- a stale legacy path or system Python installation shadowing the managed virtual
  environment.

Current development builds report boot-time configuration and local-identity
errors as concise configuration messages instead of printing a full traceback.
Treat that message as the primary failure: check the named file/key, YAML shape,
duplicate identity name, or same-class one-byte public-key prefix collision. Do
not enable debug logging merely to obtain a traceback before checking the stated
configuration error.

Use `sudo bash ./manage.sh upgrade` from the checkout to repair/migrate a managed
installation. Do not install dependencies into system Python with
`--break-system-packages`; the current service runs from
`/opt/openhop_repeater/venv`.

## Isolate software from radio hardware

Temporarily use `radio_type: null` in a copied or backed-up config. If the daemon
and dashboard then start, focus on the radio backend, device access, or wiring.
For a receive-only investigation with initialized hardware, use
`repeater.mode: no_tx`.

If `radios:` contains entries, remove that list from the diagnostic copy too:
it takes precedence for radio construction, so top-level `radio_type: null` alone
does not disable it. `monitor` disables forwarding, not every source of TX.

## Direct SX1262 problems

Verify all of the following against the exact board revision:

- Linux SPI bus and chip-select device exist;
- GPIO numbering matches the selected backend;
- reset, busy, IRQ, TXEN/RXEN, and enable pins are correct;
- DIO3 TCXO voltage and DIO2 RF-switch settings match the module;
- no other daemon is holding GPIO/SPI;
- the antenna is attached before transmit.

With `sx1262_ch341`, pin values are CH341 GPIO numbers `0-7`, not Raspberry Pi
BCM numbers. Confirm the adapter appears as VID/PID `1a86:5512` and is passed
through to a container when applicable.

## KISS, USB, or TCP modem problems

For serial backends, confirm the configured device exists, the service user can
open it, the baud rate is correct, and no terminal/modem-manager process owns it.

For `modem_tcp`, verify host, port, token, DNS/mDNS resolution, and routing from the
Repeater host. A network ping alone does not prove the modem protocol port is
reachable. For `modem_usb`, verify the USB serial device path after reconnects.
Prefer `/dev/serial/by-id/...` when available; otherwise re-check the current
`/dev/ttyACM*` or `/dev/ttyUSB*` assignment.

Docker short-form mappings cannot accept colon-containing ESP32-S3 by-id names.
Use a matching host udev rule for a colon-free name such as `/dev/openhop-modem`,
map it under `devices:`, and use the container path in config. A read-only
`/dev:/host/dev:ro` discovery mount alone does not grant access. For Proxmox,
USB-bus passthrough does not create serial-device passthrough; see
[Docker](/projects/openhop-repeater/docker/#usb-serial-device-names) and
[LXC diagnostics](/projects/openhop-repeater/proxmox-lxc/#usb-is-unavailable-inside-the-lxc).

After running the legacy terminal setup helper, also check unrelated HTTP/GPS
ports: its text-based substitutions can change same-named YAML keys. KISS uses
`baud_rate`; openHop USB uses `baudrate`. For unexpected KISS transmit latency,
check [firmware timing](/projects/openhop-repeater/kiss-setup/#optional-kiss-timing).

Then compare frequency, bandwidth, spreading factor, coding rate, preamble, sync,
LBT, and power with the modem and the mesh.

## Dashboard is unavailable

1. Confirm the service is active.
2. Test `http://localhost:8000` from the Repeater host.
3. Confirm the host is listening on the expected address and port.
4. Check host/container firewall and port mapping.
5. Review logs for HTTP bind, frontend-path, or authentication errors.

Keep port 8000 private to a trusted LAN, VPN, or protected reverse proxy. CORS is
disabled by default and should remain disabled unless a known browser client
requires it.

## Login or API failures

- Confirm the admin/guest password in the protected config, without posting it.
- Expired JWTs require a new login.
- API tokens are shown in plaintext only when created; create a replacement if a
  token was lost and revoke the old record.
- Interactive Swagger requests use the currently selected server. Verify it
  before calling a mutating endpoint.

## No packets received

- Confirm other nodes are active and use the same RF settings.
- Check antenna, feed line, connector, and placement.
- Review noise-floor, RSSI/SNR, CRC-error, and reconnect indicators.
- Verify transport-key scope and `mesh.unscoped_flood_allow` policy.
- Confirm the node is not accidentally pointed at a different serial/TCP modem.

Do not raise transmit power to diagnose receive-only problems.

## Neighbour scopes or MQTT publication are missing

Check `GET /api/mqtt_status` after scheduling a cycle. The neighbour publisher
reports a phase (`disabled`, `scheduled`, `due`, or `active`), time until the next
cycle, the last result, and the last publish timestamp.

- `disabled`: confirm the master settings block is enabled and at least one
  enabled broker has the per-broker `neighbors: true` flag.
- `scheduled`: wait until due or use the authenticated
  `POST /api/publish_neighbors` trigger.
- `active`: allow the discovery window and serialized scope queries to finish;
  a normal cycle can take several minutes.
- Repeated deferral: confirm an opted-in broker is connected and accepts the
  `neighbors` topic.
- Timeout rows: confirm the target is a fresh zero-hop repeater. Anonymous scope
  replies are rate-limited, so repeated manual queries can also time out.
- No stored scopes: inspect `GET /api/neighbor_scopes`. An empty scope string in
  a successful response means unscoped traffic only; it is not missing data.

A full cycle transmits discovery and scope requests. Verify RF settings, duty
cycle headroom, and authorization before triggering one during troubleshooting.

## Charts or history are missing

The metrics API reports whether RRD is enabled and available and whether charts
are using RRD or SQLite. If RRD is disabled or unavailable, SQLite may still
provide chart data. Check state-directory ownership and free disk space before
attempting database repair.

Never modify or vacuum the live database. Back up `/var/lib/openhop_repeater`,
stop the service, and work on a copy if offline recovery is required.

## Upgrade problems

The management script migrates legacy `pymc_repeater` directories and disables
the old service. If an upgrade fails:

1. Save the full journal locally.
2. Check whether both old and new services exist.
3. Verify the service unit points to `/opt/openhop_repeater/venv/bin/python` and
   `/etc/openhop_repeater/config.yaml`.
4. Re-run `sudo bash ./manage.sh upgrade` from a clean checkout.
5. Restore a backup only after identifying which config/state paths are active.

Docker installations are upgraded by pulling and recreating the container, not
through the dashboard updater.

Before re-running a native upgrade, update the intended clean checkout with a
fast-forward pull; `manage.sh` installs the local tree rather than pulling it.
Existing hosts need one administrator-run updated `manage.sh upgrade` to refresh
the privileged `/usr/local/bin/pymc-do-upgrade` helper. A wheel-only install or
the old web updater does not accomplish that. A writable/non-root-owned execution
tree rejection requires administrator repair from trusted packages, not loosening
permissions or making the main venv writable by `repeater`.

If a Docker upgrade breaks only the frontend, check for the removed legacy
`web.web_path: /opt/pymc_console/web/html`. Switch back to default RepeaterUI;
current images obtain optional Console functionality through the plugin catalogue.
For a local build, Git pull/restart alone is insufficient: rebuild the image with
the matching verified frontend assets.

## Plugins unavailable or failing

For native installs:

```bash
sudo systemctl status openhop-plugin-manager
sudo journalctl -u openhop-plugin-manager -n 100 --no-pager
```

- HTTP 503 from plugin operations usually means the manager/socket is unavailable;
  normal Repeater service can remain healthy. Check both processes use the same
  config, `plugins.root`, and `plugins.socket`; the default socket is
  `/var/lib/openhop_repeater/plugin-manager.sock`.
- `plugins.enabled: false` intentionally skips native unit startup. In Docker,
  `OPENHOP_PLUGIN_MANAGER=0` also disables it. Check container logs, not systemd.
  The supervisor restarts a crashed manager while Repeater remains running.
- If the native unit is missing, run the current managed upgrade as administrator;
  do not run the manager as root to work around provisioning or permissions.
- Check plugin state, settings, and logs separately from daemon logs. Five
  unexpected exits in 60 seconds trigger the plugin crash-loop limit and `FAILED`.
- After an image Python-version change, retained wheels allow plugin venv rebuilds.
  Missing wheels, unreachable dependency indexes, incompatible packages, or an
  unwritable plugin root can block recovery. Keep plugin data and repair the
  specific installation rather than deleting the entire data volume.
- HTTP 504 with `outcome: unknown` after an install means completion is ambiguous,
  not cancelled. Inspect installed status before retrying a mutation.

Plugin logs/settings can contain credentials. Redact them before sharing; plugins
and their pip dependencies are trusted code, not sandboxed workloads.

## Collect a safe support bundle

Include:

- OS and Python version;
- install type: native, Docker, HA add-on, Buildroot, or Proxmox LXC;
- Repeater commit/tag or image tag;
- selected `radio_type` and hardware model/revision;
- redacted relevant config section;
- first error and surrounding journal lines;
- what changed immediately before the failure.

Exclude private keys, JWT secrets, passwords, API tokens, MQTT/Glass/modem
credentials, exact private location, and complete databases.

For configuration details, see
[Configuration Reference](/projects/openhop-repeater/config-file/) and
[Hardware Setup](/projects/openhop-repeater/hardware-setup/).