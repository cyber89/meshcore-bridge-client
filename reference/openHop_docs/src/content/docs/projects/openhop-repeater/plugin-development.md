---
title: Plugin Development
description: Package a Python service or static application UI for the Repeater plugin manager and test its lifecycle safely.
sidebar:
  order: 18.1
---

A Repeater plugin is a wheel containing `openhop-plugin.json`, plus a Python
console-script runtime, static application assets, or both. It is **not** imported
into Repeater. Integrate through existing documented network interfaces rather
than reaching into the daemon's Python objects.

Read [Plugins](/projects/openhop-repeater/plugins/)
for deployment, credentials, lifecycle, settings, and recovery operations.

## Supported contract, not a published SDK

There is **no released plugin SDK, base class, scaffold command, or callback API**
in this source version. The extension contract is the manifest, wheel layout,
console script, environment variables, data files, and existing Repeater
interfaces. `repeater.plugins.*` implements the manager; its Python classes and
Unix IPC client are internal implementation/testing tools, not a promised stable
third-party SDK.

| Supported now | Not provided by this plugin system |
| --- | --- |
| Python service in a per-release venv | Non-Python runtime declarations |
| Static application UI at `/plugins/{id}/` | Dashboard Web Component widgets or settings-panel extensions |
| Runtime plus static UI in one wheel | In-process packet/radio hooks |
| Opaque JSON settings/defaults and optional runtime snapshot | Plugin-specific JSON Schema validation or automatic data migrations |
| Trusted process supervision | Permission scopes, signing, sandboxing, or automatic API token issuance |

Sensor drivers use a different, in-process extension mechanism. See
[Development](/projects/openhop-repeater/development/) and the
[sensor guide](https://github.com/openhop-dev/openhop_repeater/blob/dev/docs/adding_sensors.md).

## Manifest schema 1

A complete small runtime manifest:

```json
{
  "schema": 1,
  "id": "example.heartbeat",
  "name": "Example Heartbeat",
  "version": "0.1.0",
  "description": "Local heartbeat service for plugin lifecycle testing",
  "runtime": {
    "type": "python",
    "entrypoint": "example-heartbeat"
  },
  "config": {
    "defaults": {
      "interval_seconds": 10
    }
  }
}
```

`example.heartbeat` is a tutorial ID, not an official catalogue entry. Choose a
stable ID under your own naming convention before publishing: it determines the
persistent data directory and catalogue identity.

| Field | Contract |
| --- | --- |
| `schema` | `1` (manifest schema; distinct from catalogue schema 2). |
| `id` | Lowercase letters/digits plus `.`, `_`, `-`; begins with a lowercase letter or digit; at most 128 characters. No separators or `..`. |
| `name` | Nonempty display name. |
| `version` | Three numeric components such as `0.1.0`, optionally a `-` or `+` suffix. Use matching ordinary release versions in package metadata, filename, manifest, and catalogue. |
| `description` | Optional text. |
| `runtime.type` | Only `python`. |
| `runtime.entrypoint` | Bare installed console-script name, not a path, module expression, shell command, or command with arguments. |
| `ui.type` | Only `application`. |
| `ui.entry` | Relative path inside a dedicated public subtree, such as `ui/index.html`. |
| `config.defaults` | Optional JSON object, at most 256 KiB serialized. |

Declare at least one of `runtime` or `ui`; both may coexist. Supported fields do
not include requested permission scopes, automatic ports, arbitrary command-line
arguments, or generated authentication credentials.

The manager finds the manifest inside the wheel and prefers a path containing
`share/openhop/plugins/`. Package **one** manifest, conventionally at
`share/openhop/plugins/{id}/openhop-plugin.json`. Do not rely on its fallback
choice among multiple manifest files.

## Minimal Python service example

This is a documentation example you can create in your own plugin repository,
not a generated SDK template or a shipped Repeater example package. It logs a
heartbeat and writes a local runtime snapshot; it makes no network or RF calls.

Create this structure:

```text
example-heartbeat-plugin/
  pyproject.toml
  example_heartbeat.py
  openhop-plugin.json
```

Use the manifest above. In `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "example-heartbeat-plugin"
version = "0.1.0"
description = "Local openHop plugin lifecycle example"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
example-heartbeat = "example_heartbeat:main"

[tool.setuptools]
py-modules = ["example_heartbeat"]

[tool.setuptools.data-files]
"share/openhop/plugins/example.heartbeat" = ["openhop-plugin.json"]
```

Setuptools places data files under the wheel's `.data/data/` prefix. That is
compatible with the manager's `share/openhop/plugins/` manifest discovery.

In `example_heartbeat.py`:

```python
import json
import logging
import math
import os
import signal
import threading
import time
from pathlib import Path


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    plugin_id = os.environ["OPENHOP_PLUGIN_ID"]
    data = Path(os.environ["OPENHOP_PLUGIN_DATA"])
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("config.json must contain an object")
    interval = config.get("interval_seconds", 10)
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not math.isfinite(interval)
        or not 1 <= interval <= 3600
    ):
        raise ValueError("interval_seconds must be a number from 1 to 3600")

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    logging.info("Starting %s", plugin_id)
    try:
        while not stop.is_set():
            # Atomic replacement avoids exposing a partially written JSON file.
            temporary = data / ".runtime.json.tmp"
            temporary.write_text(
                json.dumps({"heartbeat_at": time.time()}), encoding="utf-8"
            )
            temporary.replace(data / "runtime.json")
            logging.info("heartbeat")
            stop.wait(interval)
    finally:
        logging.info("Stopping %s", plugin_id)
```

The manager launches the script with **no arguments**, `shell=False`, the data
directory as working directory, and these variables:

| Variable | Meaning |
| --- | --- |
| `OPENHOP_PLUGIN_ID` | Manifest/installed plugin ID. |
| `OPENHOP_PLUGIN_DATA` | Absolute persistent data directory for that ID. |

The rest of the manager's environment is inherited except the legacy
`OPENHOP_PLUGIN_GITHUB_TOKEN`. There is no injected Repeater token or API URL.
Explicitly document any additional environment/configuration your plugin needs;
never assume a privileged credential will appear.

### Runtime design requirements

- Keep the main process in the foreground. Do not daemonize or detach workers.
  An unexpected exit, even code zero, counts toward crash supervision.
- Handle SIGTERM promptly. The default stop grace is five seconds, then the
  manager kills the supervised process group. Commit important data before the
  deadline; do not depend on a long shutdown handler.
- Log useful state changes to stdout/stderr, flush promptly, and redact secrets.
  Captured logs are bounded; they are not an audit archive.
- Store mutable data only beneath `OPENHOP_PLUGIN_DATA` by convention. The release
  and venv are replaceable. This convention is not enforced OS containment.
- Use timeouts and bounded reconnect/backoff when connecting to external services.
  A process can be `RUNNING` while its integration is disconnected.
- Own configuration validation and data migrations. Make upgrades and any supported
  downgrade explicit; the manager does not interpret or restore your database.

## Settings and runtime snapshots

Read settings from `$OPENHOP_PLUGIN_DATA/config.json`. The settings API replaces
the entire object; it does not merge partial updates. Decide whether the process
reads settings only at startup or implements its own safe reload. The operator can
request a restart with a settings save.

You can also package `config.default.json` next to the manifest. Add that filename
to the same setuptools data-files list. Its keys override matching manifest
defaults when the manager constructs the initial settings. Seeding only occurs
when `data/config.json` is missing, and no file is seeded for empty defaults.
New defaults do not automatically migrate an existing configuration. Never ship
real credentials in either defaults source.

For an optional status snapshot, atomically write a JSON object to
`$OPENHOP_PLUGIN_DATA/runtime.json`. The existing authenticated endpoint
`GET /api/plugins/runtime?id={id}` returns `id`, `path`, `exists`, and `runtime`.
The manager imposes no application-specific field schema and does not turn it
into a readiness probe. Include timestamps and meaningful connection state in
your own format; omit secrets and avoid unbounded snapshots. A missing file
returns an empty object with `exists: false`.

## Add an application UI

Add this manifest field (or remove `runtime` for a UI-only application):

```json
{
  "ui": {
    "type": "application",
    "entry": "ui/index.html"
  }
}
```

This is a field fragment to merge into the complete manifest, not a complete
manifest itself. Package your built files under that subtree, for example:

```toml
[tool.setuptools.data-files]
"share/openhop/plugins/example.heartbeat" = ["openhop-plugin.json"]
"share/openhop/plugins/example.heartbeat/ui" = ["ui/index.html"]
"share/openhop/plugins/example.heartbeat/ui/assets" = ["ui/assets/app.js"]
```

Replace the earlier `[tool.setuptools.data-files]` table rather than duplicating
it. Enumerate all required asset directories/files in your packaging configuration;
a successful frontend build alone does not put assets into the wheel.

When enabled, `ui/index.html` is served at `/plugins/example.heartbeat/`, and
`ui/assets/app.js` at `/plugins/example.heartbeat/assets/app.js`. The public URL
omits the `ui/` directory. Configure your frontend base/router path for
`/plugins/example.heartbeat/` and test deep-link reloads. Missing paths fall back
to the entry document for SPAs, so a 200 response alone does not prove a requested
JavaScript file exists: inspect content type and body.

The manifest rejects release-root `index.html`, absolute paths, parent/dot
segments, and reserved roots `venv`, `data`, `logs`, `releases`, or `current`.
Serving also rejects traversal and UI symlinks escaping the dedicated asset
subtree. A legacy plugin with an invalid layout must be repackaged, not granted
access to the whole release directory.

Static assets are public, same-origin content. API calls still need authentication;
there is no automatic UI permission scope or plugin credential. Never bundle
secrets into assets, and do not confuse a dedicated directory with browser-origin
isolation. Plugin UIs are applications, not dashboard widgets. For UI-only wheels
the manager extracts assets and does not create/install a Python runtime venv;
`enabled: true` with state `STOPPED` is expected.

## Build and inspect your wheel

In your own plugin checkout, use an isolated build environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install build
python -m build --wheel
python -m zipfile -l dist/example_heartbeat_plugin-0.1.0-py3-none-any.whl
```

These are standard Python packaging commands for the example, not an openHop SDK
build command. Keep build outputs clean between releases and inspect the actual
wheel for:

1. Exactly one valid manifest in the expected share subtree.
2. Matching package/manifest versions and an appropriate Python/ABI/platform tag.
3. The console-script entry in `.dist-info/entry_points.txt` and its importable
   Python module.
4. Every declared UI/default file, with no credentials, developer venv, database,
   local logs, or stale generated bundles.
5. Dependencies appropriate for target Python versions and CPU architectures.
   A pure-Python plugin can still depend on platform-specific binary packages.

Runtime installation creates a venv using the manager's Python and runs that
venv's `python -m pip install --upgrade <wheel>`. It does not use the Repeater venv
as the installation target. Package dependencies explicitly instead of assuming
Repeater's installed libraries are visible in the plugin environment.

The manager bounds wheel downloads/staging at 100 MiB. Archive validation also
limits expanded size to 256 MiB, a member to 16 MiB, archive members to 4096, and
metadata reads to 1 MiB. Budget assets accordingly. Venv creation and pip execution
have separate default timeouts of 120 and 300 seconds. Test slow or binary-heavy
dependency installations on the actual target architecture.

## Safe development and acceptance testing

### Run the example without Repeater

After installing your built wheel into a disposable development venv:

```bash
python -m pip install dist/example_heartbeat_plugin-0.1.0-py3-none-any.whl
export OPENHOP_PLUGIN_ID=example.heartbeat
export OPENHOP_PLUGIN_DATA="$(mktemp -d /tmp/openhop-heartbeat.XXXXXX)"
example-heartbeat
```

The tutorial runs indefinitely; use Ctrl-C to verify graceful shutdown. Read the
runtime snapshot in the temporary directory. Test invalid settings and restart
behavior before using a manager. This test proves the console script, not manager
installation or HTTP integration.

### Exercise an isolated manager

Use a separate Repeater development checkout/venv as described in
[Development](/projects/openhop-repeater/development/). Start a manager without a
production config, using explicit disposable paths:

```bash
python -m repeater.plugins \
  --plugins-root /tmp/openhop-plugin-lab/plugins \
  --socket /tmp/openhop-plugin-lab/manager.sock \
  --log-level DEBUG
```

Choose an unused, private writable lab directory first. Never point this at live
plugin data or a live socket. This starts the manager only, not a radio daemon.
In another terminal in the same development environment, the **internal** IPC
client can exercise the manager for a local test:

```python
from pathlib import Path
from repeater.plugins.ipc import PluginIPCClient

client = PluginIPCClient("/tmp/openhop-plugin-lab/manager.sock")
wheel = Path("/absolute/path/to/example_heartbeat_plugin-0.1.0-py3-none-any.whl")
assert wheel.is_file()
installed = client.install(str(wheel))
assert installed["id"] == "example.heartbeat"
assert installed["enabled"] is False
client.enable("example.heartbeat")
status = client.status("example.heartbeat")
assert status["state"] == "RUNNING"
client.disable("example.heartbeat")
assert client.status("example.heartbeat")["state"] == "DISABLED"
```

This is a source-level test aid, not the public SDK. For end-to-end acceptance,
use the authenticated HTTP upload/settings/lifecycle calls in
[Advanced Plugin Administration](/projects/openhop-repeater/plugin-administration/)
on an isolated Repeater instance. Use temporary config/storage and a null radio
for tests that do not require hardware; normal startup can generate identities
and secrets or connect/transmit when real hardware/config is selected.

Check all of these before release:

- Fresh local upload is disabled; configuration and enable start the correct script.
- Status PID and logs correspond to this release, and the runtime snapshot advances.
- Required API/Companion/upstream connections actually succeed; retry loops are not readiness.
- Stop and disable remove ordinary child workers, and disable survives manager restart.
- Invalid settings produce an actionable error without leaking credentials.
- UI assets load at the plugin base path, deep links work, disabled UIs are hidden,
  and private runtime/default/data files are not served.
- A versioned upgrade preserves settings/data, stops old runtime code, and starts
  the new runtime; failed install and interrupted rebuild recovery are tested.
- Default uninstall retains data, reinstall reuses it, and explicit data deletion
  only removes intended plugin data.

Do not promise automatic rollback: current release directories and archived
wheels support recovery but there is no public rollback transaction endpoint.
If your data format is not backward-compatible, document a restore procedure.

### Repeater regression tests

From the Repeater development checkout with its dev dependencies installed:

```bash
python -m pytest -q tests/test_plugin_*.py
python -m ruff check repeater/plugins repeater/web/plugin_endpoints.py tests/test_plugin_*.py
python scripts/check_openapi_contract.py
```

Useful implementation test references:

| Source test | Coverage to reuse or extend |
| --- | --- |
| `tests/test_plugin_manifest.py` | Manifest fields, IDs, runtime/UI path rejection. |
| `tests/test_plugin_manager_lifecycle.py` | Install layout, isolated venv commands, states, config, restart/rebuild, data retention using temporary paths/mocks. |
| `tests/test_plugin_github_catalogue_install.py` | Schema-2 approved wheel install/update, checksum and ID/version checks, no GitHub API lookup. |
| `tests/test_plugin_api_endpoints.py` | Request payloads and manager forwarding at handler level; not a full authentication/HTTP-dispatch test. |
| `tests/test_plugin_timeout_openapi.py` | Unknown outcomes and OpenAPI timeout documentation. |
| `tests/test_plugin_progress.py` | Bounded progress and SSE behavior. |
| `tests/test_plugin_static_security.py` | Public asset subtree boundary and SPA fallback. |
| `tests/test_plugin_runtime_hardening.py` | Installer/process/log/rebuild hardening. |
| `tests/test_plugin_ipc_hardening.py` | Concurrent IPC, timeouts, and upload ownership. |
| `tests/test_plugin_container_supervisor.py` | Container service supervision. |

Unit fixtures can mock pip and subprocesses. Do not mistake a synthetic test ZIP
or a mocked pip success for a distributable wheel: verify an actual built wheel
in a clean target environment. If using fake PIDs, mock process-group signaling
so tests cannot signal real host processes. For changes to API dispatch, test
actual HTTP query handling as well as direct handler calls.

The repository also contains
[`scripts/docker-plugin-smoke.sh`](https://github.com/openhop-dev/openhop_repeater/blob/dev/scripts/docker-plugin-smoke.sh).
It is an integration harness, **not** a read-only check: it creates and removes
containers/volumes and performs plugin operations. Review it and run only with
an explicitly designated disposable image/environment. Follow the broader
[Development](/projects/openhop-repeater/development/) checks for backend changes.

## Publish for catalogue approval

Publish a versioned wheel as a GitHub Release asset in your plugin repository.
Use an immutable release artifact: replacing bytes after approval breaks the
checksum. Keep the exact wheel filename/version aligned with its manifest.
Compute the digest on the wheel you will actually publish:

```bash
sha256sum dist/example_heartbeat_plugin-0.1.0-py3-none-any.whl
```

The schema-2 catalogue metadata needed for an approved entry includes:

| Field | Value to supply to catalogue maintainers |
| --- | --- |
| `id`, `name`, `description` | Plugin identity and useful description. |
| `repository` | GitHub `owner/repository`, not an arbitrary package index. |
| `version` | Exact manifest version, e.g. `0.1.0`. |
| `wheel_url` | `https://github.com/owner/repository/releases/download/tag/distribution-0.1.0-py3-none-any.whl`. |
| `sha256` | Lowercase 64-character SHA-256 of that exact wheel. |
| `category` | Optional catalogue grouping. |

The URL must be a wheel in the declared repository's GitHub Release path, with a
filename containing the approved version; query strings and fragments are not
accepted. Approval checks require manifest ID/version agreement as well as the
digest. Publication alone does not add or update the curated catalogue: coordinate
approval with its maintainers. This Repeater repository implements consumption,
not a documented maintainer submission CLI or automatic approval workflow.

Provide installation requirements, supported architectures/Python versions,
required Companion/API services, config keys/defaults, credential privileges,
ports/network access, logging, data migration/backup, and uninstall behavior in
your own README. Describe dependency pinning honestly: the catalogue checksum
covers your wheel, **not** pip's transitive downloads. Rebuilding a venv after a
Python change may resolve different dependencies unless the deployment controls
them. Test against a controlled dependency source when reproducibility matters.

## Source reference

- [Upstream plugin guide](https://github.com/openhop-dev/openhop_repeater/blob/dev/docs/plugins.md)
- [Manifest validator](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/manifest.py)
- [Runtime installer and process contract](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/runtime.py)
- [Manager lifecycle/settings/update implementation](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/manager.py)
- [Filesystem contract](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/storage.py)
- [Manager CLI](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/__main__.py) and [internal IPC](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/ipc.py)
- [Static serving](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/web/http_server.py) and [plugin HTTP API](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/web/plugin_endpoints.py)
- [Catalogue validation](https://github.com/openhop-dev/openhop_repeater/blob/dev/repeater/plugins/catalogue.py)
- [Regression tests](https://github.com/openhop-dev/openhop_repeater/tree/dev/tests) and [Repeater package metadata](https://github.com/openhop-dev/openhop_repeater/blob/dev/pyproject.toml)
