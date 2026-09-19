---
title: Advanced Plugin Administration
description: Plugin-manager provisioning, API automation, storage, and recovery for administrators.
sidebar:
  order: 18.2
---

For normal use, start with the [dashboard plugin guide](/projects/openhop-repeater/plugins/).
This reference covers host provisioning, API automation, and deeper recovery;
you do not need curl or an API token to manage plugins in the dashboard.

Repeater plugins are **external applications**, not Python modules loaded into the
Repeater daemon. A separate plugin manager installs wheels, maintains persistent
data, and supervises Python services. Plugins can also provide a static application
UI, or combine a service and UI. They communicate through existing Repeater
interfaces such as REST, WebSockets, and the Companion frame server.

Older Repeater packages may not include the manager; follow the native upgrade
or container image update guidance below before installing plugins. For authoring and packaging, see [Plugin development](/projects/openhop-repeater/plugin-development/).
These applications are separate from the in-process sensor extensions described
in [Development](/projects/openhop-repeater/development/).

## Trust before installation

:::caution[Process separation is not a sandbox]
Install only applications **and dependencies** you trust. Native plugins run as
`repeater`; container plugins use the container account. Separate processes and
virtual environments isolate Python dependencies, not files, networks, credentials,
or other plugins. Do not run the manager as root to fix permissions.
:::

- Repeater API tokens are administrator-equivalent, including plugin installation
  and settings access. They are not read-only telemetry credentials.
- Schema-2 catalogue verification covers the approved wheel's SHA-256, **not**
  dependencies downloaded by pip. A trusted catalogue is not a fully hash-locked
  environment or a code-signing system.
- Enabled plugin UI assets are served publicly at the Repeater origin. Do not
  place secrets in their HTML, JavaScript, or asset directory. Treat their scripts
  as trusted same-origin application code; API authentication is a separate boundary.
- The manager inherits its environment when launching plugins (with the legacy
  `OPENHOP_PLUGIN_GITHUB_TOKEN` removed). Do not put unrelated secrets in the
  manager environment.
- Stop/disable terminate the supervised process group, including ordinary child
  workers. This does not contain malicious processes that deliberately detach.

See [Security and authentication](/projects/openhop-repeater/security-and-authentication/)
for the wider Repeater access model.

## Provision the manager

### Native installation

Current `manage.sh` install/upgrade paths provision
`openhop-plugin-manager.service` alongside `openhop-repeater.service`. On an
existing native installation, run the **updated, trusted** management script's
upgrade once as an administrator:

```bash
sudo bash ./manage.sh upgrade
```

Run this from your reviewed Repeater checkout, not an arbitrary downloaded script.
It is a full native upgrade, not a read-only plugin setup command. This step also
refreshes the root-owned OTA helper; installing only a Python wheel cannot safely
replace an old privileged helper. Subsequent OTA upgrades use the service unit
bundled in the installed Python package, without requiring a source checkout.

Check the exact native service:

```bash
systemctl status openhop-plugin-manager --no-pager
journalctl -u openhop-plugin-manager -n 100 --no-pager
```

The shipped unit uses `/opt/openhop_repeater/venv/bin/openhop-plugin-manager`,
`/etc/openhop_repeater/config.yaml`, and the `repeater` account. A custom install
must adapt those paths and provide writable plugin storage and socket parent.
Do not make the application venv service-writable: privileged upgrade helpers
reject untrusted/writable execution trees. An administrator must repair a failed
trust check from a trusted package rather than bypass it.

### Docker

The standard image runs Repeater and the manager through a process supervisor,
with `tini` as PID 1. It forwards shutdown signals and restarts an unexpectedly
exited manager while Repeater remains running. No systemd service is needed
inside the container.

Persist `/var/lib/openhop_repeater` (the normal data volume), which includes plugin
releases, archived wheels, settings, and data. Keep the config and data mounts
writable by the configured container account. A wheel path supplied in JSON is a
path **inside the container**, not on the browser's machine or the Docker host.
See [Docker](/projects/openhop-repeater/docker/) for volume setup.

Set container environment `OPENHOP_PLUGIN_MANAGER=0` to run without the manager.
The YAML switch below also opts out. Neither option uninstalls saved plugins.

### Configuration

```yaml
plugins:
  enabled: true
  # Defaults are under storage.storage_dir:
  # root: "/var/lib/openhop_repeater/plugins"
  # socket: "/var/lib/openhop_repeater/plugin-manager.sock"
  catalogue_url: "https://repeater-plugins.openhop.dev/catalogue.json"
```

`enabled` defaults to enabled when omitted. `false` prevents manager startup;
it is not the same as disabling one installed plugin. Apply startup/path changes
by restarting the affected service(s) or recreating the container; do not assume
live reload. Repeater and manager must resolve the **same** root and socket.
Prefer absolute custom paths, and use a short socket path on systems with Unix
socket pathname limits. The socket is created with mode `0660`; membership of
its service group is a management privilege, not a read-only permission.

Repeater can operate without the manager. Missing/unreachable manager IPC yields
HTTP **503** from management APIs, not a requirement to stop radio operation.
Static UI serving reads installed state separately from manager IPC.

## Install an application

The dashboard Plugins page provides installation and settings controls. The API
workflow below is also useful when the UI is unavailable or for repeatable admin
operations. Create an API token through the authenticated dashboard and send it
in `X-API-Key` (JWT sessions instead use `Authorization: Bearer`). In these shell
examples, set `OPENHOP_API_KEY` privately and do not paste it into logs or tickets.
Use HTTPS for remote access; the example uses host-local HTTP.

```bash
BASE='http://127.0.0.1:8000'
# List approved catalogue entries, then choose an actual returned ID.
curl --fail-with-body -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/catalogue"
```

### From the catalogue

The default static catalogue is hosted at
`https://repeater-plugins.openhop.dev/catalogue.json`. Its schema 2 specifies the
currently approved version, exact GitHub Release wheel URL, and lowercase SHA-256.
The manager validates repository/URL boundaries, checksum, manifest ID, and
manifest version before installation. It only follows permitted HTTPS redirects.

A newer GitHub Release is **not** automatically approved. Default catalogue
browsing and update checks do not query the GitHub API and need no GitHub token.
Custom schema-1 repository-only catalogues remain supported but use legacy
GitHub release discovery and do not provide the schema-2 checksum approval model.
Catalogue results are cached for ten minutes; use `?refresh=true` to request a
fresh catalogue.

The following uses `openhop.nomad` as an example ID, not a guarantee of current
catalogue availability:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"id":"openhop.nomad"}' "$BASE/api/plugins/catalogue_install"
```

**Catalogue installs enable the plugin immediately**, starting a runtime if
present. Review defaults and required connections before installing. Disable it
while configuring if it must not run yet. An optional `version` cannot select an
unapproved version from a schema-2 entry.

### From a local wheel

Download/build a trusted `.whl` compatible with the host's Python and platform.
Upload it without installing it into the Repeater venv yourself:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" \
  -F 'wheel=@/path/to/plugin-0.1.0-py3-none-any.whl' \
  "$BASE/api/plugins/install"
```

Alternatively, when the wheel already exists on the server and is readable by
both the HTTP process and manager:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"wheel_path":"/absolute/server/path/plugin-0.1.0-py3-none-any.whl"}' \
  "$BASE/api/plugins/install"
```

A **new local installation is disabled**. Configure it, then enable it. Reinstall
preserves the enabled flag, but local install is not the stop/swap/restart update
workflow: stop or disable an existing runtime before replacing its wheel and
explicitly start/enable it afterwards. Do not overwrite running code in place.
Local installation does not apply catalogue checksum approval. New local-only
installs lack repository metadata, so catalogue update checks are unavailable;
upload a reviewed replacement wheel or deliberately install from the catalogue.

Runtime wheels get a version-specific venv. UI-only wheels have their assets
extracted without a Python runtime venv. Dependency resolution may need network
access even when the wheel is local; offline use requires a suitable controlled
pip dependency source.

## Settings and required services

Plugin settings are a JSON object in `data/config.json`, **not** extra keys in
Repeater's YAML. The manager stores an opaque object and does not validate the
plugin's hostnames, ports, credentials, or other application-specific keys.

```bash
curl --fail-with-body -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/settings?id=openhop.nomad"
```

The response includes `exists`, `saved`, `defaults`, and editor-facing `config`.
When no saved settings exist, defaults come from manifest `config.defaults` and
an optional packaged `config.default.json`; the latter overrides matching keys.
An empty saved object may also display defaults in the editor. Inspect `saved`
and `exists` when distinguishing a template from persisted settings.

To save, send the **complete replacement object**, not a partial patch. The example
keys below belong to NOMAD, not the generic plugin manager:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"id":"openhop.nomad","restart":true,"config":{"meshcore_host":"127.0.0.1","meshcore_port":5001,"nomad_url":"http://127.0.0.1:8080","nomad_model":"qwen2.5:3b-instruct"}}' \
  "$BASE/api/plugins/settings"
```

Settings are limited to 256 KiB. `restart` defaults to false and only restarts an
enabled runtime plugin. A response saying **config saved but restart failed**
means the file has already changed: read settings and logs before retrying.
The dashboard's Config dialog edits the same file and offers Reset to defaults;
review and save the resulting object rather than assuming defaults migrate data.
Existing non-missing configuration is not overwritten during an install/update.

A bridge using the Companion frame server needs that server enabled separately.
For NOMAD, upstream's acceptance workflow expects a reachable Companion endpoint
and a reachable NOMAD service. In the standard single container, `127.0.0.1:5001`
means that container's frame server. It does **not** reach a service running only
on the Docker host. Check actual connection messages, not just `RUNNING`.

## Enable, stop, and inspect

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"id":"openhop.nomad"}' "$BASE/api/plugins/enable"

curl --fail-with-body -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/openhop.nomad"
curl --fail-with-body -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/logs?id=openhop.nomad&tail=100"
```

All lifecycle operations below use `POST`, the same JSON `{"id":"…"}`, and the
same authentication as `enable`:

| Endpoint under `/api/plugins/` | Effect |
| --- | --- |
| `enable` | Persist enabled=true; start a runtime; expose an application UI. |
| `disable` | Stop runtime and persist enabled=false; hide its application UI. |
| `start` | Start an already-enabled runtime. Disabled plugins must be enabled first. |
| `stop` | Stop runtime without clearing enabled; it can start again on manager boot. UI exposure is unchanged. |
| `restart` | Stop and start an enabled runtime. |

`GET /api/plugins/` lists installed plugins. Status includes ID, version, enabled
flag, state, PID, last exit code, runtime/UI flags, source/repository, and data
path. States are `DISABLED`, `STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, and
`FAILED`. An enabled UI-only application normally reports `STOPPED`: it has no
process to run. Open its assets at `/plugins/{id}/`.

Runtime stdout/stderr go to `logs/plugin.log`; capture is bounded at 5 MiB and can
truncate older output. Five unexpected exits within sixty seconds stop automatic
restarts and leave `FAILED`. Even exit code zero is unexpected for a service that
was supposed to remain running. Fix the cause before restarting.

An optional plugin-written `data/runtime.json` can be read with
`GET /api/plugins/runtime?id={id}`. It is application data, not a manager health
probe; a missing snapshot is not by itself a failure.

## Updates, progress, and backups

Before upgrading, stop/disable the plugin if necessary and back up its persistent
`data/`, including settings, using the plugin's own database-consistency guidance.
Retain the old wheel and record the installed version. The manager does not
migrate or roll back application-owned data for you.

```bash
curl --fail-with-body -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/updates?id=openhop.nomad&refresh=true"
curl --fail-with-body -X POST \
  -H "X-API-Key: $OPENHOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"id":"openhop.nomad"}' "$BASE/api/plugins/update"
```

The update route downloads/verifies the selected wheel, stops the runtime,
installs the new release, preserves the enabled flag, and restarts it if enabled.
A schema-2 update with no newer approved version is a no-op. Update failure does
**not** promise automatic restart of the old process or transactional rollback.
Always read back status/version and check the application's real connections.

Catalogue install/update progress is available as authenticated SSE:

```bash
curl -N -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/progress?id=openhop.nomad&fresh=true"
```

Open that stream before submitting the operation in another terminal. `fresh`
ignores an already-finished previous operation. Events contain JSON `type` values
such as `connected`, `line`, `status`, `done`, and `keepalive`. Progress is bounded,
in-memory, and not a durable job history; a stream timeout is not cancellation.
Local wheel upload does not use the same catalogue progress recording path.

:::caution[An unknown outcome is not a failed transaction]
HTTP 504 with `outcome: "unknown"` means transport was lost after dispatch and the
operation **may still complete**. Read status, progress, and logs before retrying.
Do not delete an ambiguously accepted upload or start a competing install.
HTTP 409 indicates a conflicting operation on the same plugin; wait and inspect.
:::

### Storage and recovery

The normal layout under `/var/lib/openhop_repeater/plugins/{id}/` is:

```text
releases/0.1.0/
  openhop-plugin.json
  plugin-0.1.0-py3-none-any.whl
  venv/                  # runtime plugins only
  ui/                    # optional static assets
current -> releases/0.1.0
data/
  config.json            # optional settings
  runtime.json           # optional plugin snapshot
logs/plugin.log
state.json               # manager-owned version/enabled/provenance
```

Older release directories can remain; they are not a public rollback selector.
Do not edit `state.json` or retarget `current` as normal administration. For a
reviewed local recovery, disable the plugin, preserve/back up its data, install a
known-good wheel through the local install endpoint, restore compatible data if
needed, and enable it. Confirm status and actual application behavior. A local
reinstall of an existing catalogue plugin can retain its prior provenance; it is
not a way to clear update metadata or pin catalogue updates permanently.

Persisted venvs can outlive a container Python minor-version change. On start,
the manager can rebuild from the release's archived wheel. A failed rebuild
restores the previous venv and remains retryable; interrupted rebuild intent is
reconciled on restart. This is process-interruption recovery, not guaranteed
power-loss durability, and unused backups can remain. Keep the archived wheel;
rebuilds may still need dependency downloads and a compatible upstream package.

| Symptom | Check and recovery |
| --- | --- |
| Manager unavailable / 503 | Unit/container logs, opt-out flags, root/socket agreement, socket permissions. Do not restart the radio daemon blindly. |
| Install fails at venv/pip | Manager logs/progress, free space, Python/platform compatibility, dependency reachability, writable data volume. Do not use root pip in the Repeater venv. |
| Checksum, ID, version, or URL rejected | Stop and verify release/catalogue metadata with the publisher; do not bypass approval checks. |
| `FAILED` / repeated exits | Plugin logs, settings validity, missing executable/dependencies, required service availability. Fix, then restart/enable. |
| `RUNNING` but not working | Verify real Companion/API/upstream connection and plugin runtime snapshot, not just PID. |
| Plugin UI 404 | Confirm enabled=true, `has_ui`, dedicated packaged UI subtree, and entry file. Repackage legacy root-level `index.html` manifests. |
| Catalogue/download outage | Existing installs and Repeater startup continue. Retry catalogue later; a trusted local wheel remains an option. |
| Settings read error | Preserve the file, repair invalid JSON/object content with the plugin's guidance, then reread. Do not discard data to make the editor load. |

## Uninstall without losing data

Default uninstall stops the plugin and removes its release code, current link,
and manager state, but **keeps `data/` and `logs/`**:

```bash
curl --fail-with-body -X DELETE -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/openhop.nomad"
```

Verify it disappears from `GET /api/plugins/`. Reinstalling the same ID can reuse
retained settings/data. Export diagnostic logs before uninstall if needed.

To intentionally delete the plugin's persistent data as well, back it up first
and use:

```bash
curl --fail-with-body -X DELETE -H "X-API-Key: $OPENHOP_API_KEY" \
  "$BASE/api/plugins/openhop.nomad?delete_data=true"
```

There is also `POST /api/plugins/uninstall` with `id` and optional boolean
`delete_data`. Uninstall does not clean up services or files a trusted application
created outside its plugin directory. Removing one plugin is separate from
[uninstalling Repeater](/projects/openhop-repeater/uninstallation/).

## Implementation references

- [Upstream plugin guide](https://github.com/openhop-dev/openhop_repeater/blob/dev/docs/plugins.md)
- [Configuration defaults](https://github.com/openhop-dev/openhop_repeater/blob/dev/config.yaml.example)
- [API handlers](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/web/plugin_endpoints.py) and [OpenAPI](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/web/openapi.yaml)
- [Lifecycle manager](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/manager.py), [runtime](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/runtime.py), and [storage](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/storage.py)
- [Native provisioning](https://github.com/openhop-dev/openhop_repeater/blob/dev/manage.sh), [service unit](https://github.com/openhop-dev/openhop_repeater/blob/dev/openhop-plugin-manager.service), and [container supervisor](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/container_supervisor.py)
