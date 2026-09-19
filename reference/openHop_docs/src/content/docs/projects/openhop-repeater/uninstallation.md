---
title: Uninstallation
description: Remove openHop Repeater while making an explicit decision about configuration, identities, logs, and persistent data.
sidebar:
  order: 19
---

:::danger
The native `manage.sh uninstall` action is a complete removal. After one
confirmation it deletes the current and legacy installation, configuration, logs,
data, and the `repeater` service user. It does not ask a separate question for each
data directory.
:::

This page tracks `manage.sh` at Repeater `dev` commit
[`ffd239d`](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/manage.sh).
Both Repeater and plugin-manager services are removed. The script does not offer
per-directory preservation prompts.

## Decide whether you want removal or a clean reset

Use uninstallation only when the application and its host-managed data should be
removed. For a configuration reset, migration, or repair, use the applicable
management operation or restore procedure instead.

Separate these categories before continuing:

| Category | Native path | Why it matters |
| --- | --- | --- |
| Application and virtual environment | `/opt/openhop_repeater` | Installed code and Python environment |
| Configuration | `/etc/openhop_repeater` | Radio, identity paths, HTTP, storage, MQTT, and service settings |
| Runtime data | `/var/lib/openhop_repeater` | Application state, identity files, databases, charts, and other persistent data |
| Plugins (default root) | `/var/lib/openhop_repeater/plugins` | Releases, retained wheels, venvs, settings, plugin data/logs, and manager state; deleted with runtime data |
| Logs | `/var/log/openhop_repeater` | File-based logs where enabled; journald is managed separately |
| Legacy pyMC paths | `/opt/pymc_repeater`, `/etc/pymc_repeater`, `/var/lib/pymc_repeater`, `/var/log/pymc_repeater` | Removed by the same current uninstaller |

The exact contents depend on configuration. Inspect paths without printing private
keys, passwords, tokens, transport keys, or complete secret-bearing configuration.

## Make a durable backup first

The uninstaller attempts to copy `/etc/openhop_repeater` to a timestamped directory
under `/tmp`, then deletes the original. That copy is best-effort, covers only the
configuration directory, and may disappear on reboot or automated cleanup. It is not
a sufficient backup for identities and runtime data.

Before invoking the uninstaller:

1. Stop application changes or RF operation if required by the deployment.
2. Copy configuration and required runtime data to durable storage outside all paths
   listed above.
3. Include identity files and any external files referenced by configuration.
4. Preserve ownership and restrictive permissions.
5. Verify the backup can be read by the intended recovery process without printing
   its secrets.
6. Record the exact source commit or container digest being removed.

Do not place the only backup under `/tmp` or inside a directory the uninstaller will
delete.

See [Identity Management](/projects/openhop-repeater/identity-management/) and
[Security and Authentication](/projects/openhop-repeater/security-and-authentication/)
for secret-handling boundaries.

## Native managed installation

Run the action from the same reviewed Repeater checkout or installed management
script used to manage the host:

```bash
sudo bash ./manage.sh uninstall
```

The script requires root and obtains the global management lock. After the single
confirmation it performs these actions:

1. stops and disables `openhop-plugin-manager.service` and `openhop-repeater.service`;
2. attempts a configuration-only backup under `/tmp`;
3. removes both service units from `/etc/systemd/system` and reloads systemd;
4. removes the Repeater polkit, sudoers, and upgrade-helper files;
5. recursively deletes all current install/config/log/data paths;
6. recursively deletes all listed legacy pyMC paths;
7. deletes the `repeater` service user when present.

These removals are not individually optional. Cancel at the confirmation screen if
the durable backup or scope is not correct.

This differs from uninstalling **one plugin**, which preserves that plugin's
`data/` by default unless data deletion is explicitly requested. Native Repeater
uninstallation deletes the default plugin root along with all runtime data. A
custom `plugins.root` outside the listed directories is not automatically covered
by these recursive deletions; back up and review it separately.

The script does not document removal of every dependency package, hardware group,
host udev rule, or journald record installed elsewhere on the system. Review those
host-level items separately and remove them only when no other application uses them.

## Verify native removal

After the script reports success, verify state rather than trusting the dialog alone:

```bash
systemctl is-enabled openhop-repeater.service
systemctl is-active openhop-repeater.service
systemctl cat openhop-repeater.service
systemctl is-enabled openhop-plugin-manager.service
systemctl is-active openhop-plugin-manager.service
systemctl cat openhop-plugin-manager.service
```

The service should be absent/inactive. Also verify the four current application paths
and any migrated legacy paths are absent. Check that the intended durable backup is
outside those paths and still readable.

A retained journald history does not mean the service is still installed. Conversely,
a missing dashboard alone does not prove files and service state were removed.

## Docker Compose removal

Container removal and data removal are separate operations.

From the deployment directory, stop and remove the container/network while preserving
named volumes:

```bash
docker compose down
```

Current images stop Repeater and the plugin manager together through their
supervisor. Keeping the data volume also keeps plugin releases, settings, and
data; custom plugin-root mounts require separate handling.

The repository Compose file uses named volumes for:

- `/etc/openhop_repeater` configuration;
- `/var/lib/openhop_repeater` data.

`docker compose down` preserves those named volumes by default. Record their actual
names before deleting the deployment directory:

```bash
docker volume ls
```

If the deployment uses bind mounts, data remains at the configured host paths instead.
Back up and inspect those paths separately.

:::danger
Do not add `--volumes` or run a bulk volume-prune command unless you have verified
the exact volume names, made a durable backup, and intentionally want permanent
data loss. A shared or misidentified volume can affect another service.
:::

After removing a container but retaining data, confirm no container still mounts the
volumes before moving or deleting them. Hardware udev rules and host device permissions
also live outside the container and are not removed by Compose.

## Home Assistant, Unraid, and other wrappers

Remove wrapper-managed deployments through the owning platform first. Their storage,
container names, update channels, and backup facilities can differ from the native
script and repository Compose file.

- For Home Assistant, preserve add-on configuration and platform backups according to
  the add-on documentation.
- For Unraid, preserve mapped appdata/config/data paths and inspect the template's
  actual mappings before deleting the application.
- Do not run the native host uninstaller inside a managed container unless that
  wrapper explicitly documents it.

## Reinstallation and recovery

A later native install recreates the service user and default directories, but it does
not reconstruct deleted identities or application data. Restore only after verifying:

- the target source commit and expected configuration schema;
- file ownership for the recreated `repeater` account;
- identity and secret permissions;
- radio backend/device paths;
- storage/database compatibility.

Start in `null`/no-radio mode where practical, validate the dashboard and data, then
restore hardware/RF operation deliberately.

## Related pages

- [Installation](/projects/openhop-repeater/installation/)
- [Docker Deployment](/projects/openhop-repeater/docker/)
- [Identity Management](/projects/openhop-repeater/identity-management/)
- [Security and Authentication](/projects/openhop-repeater/security-and-authentication/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
