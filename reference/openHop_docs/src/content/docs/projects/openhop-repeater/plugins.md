---
title: Plugins
description: Find, install, configure, open, update, and remove plugins from the Repeater dashboard.
sidebar:
  order: 10.5
---

Use **System → Plugins** in the Repeater dashboard to add applications and
background services. Normal plugin management happens here: you do not need a
terminal, curl, or an API token.

A plugin can be a **Service**, a **UI app**, or both. Services run in the
background; UI apps provide a browser interface. These are separate from the
built-in sensor modules that collect telemetry.

:::caution[Install only plugins you trust]
Plugins and their dependencies run with the service/container account's access.
They are not sandboxed. Review the publisher's instructions before installation,
especially required credentials, connections, and persistent data.
:::

## Open the Plugins page

1. Sign in to your Repeater dashboard as an administrator.
2. Expand **System** in the sidebar and select **Plugins**.
3. Use **Catalogue** to find applications or **Installed** to manage ones already
   on this Repeater.

The top **Refresh** button reloads installed state. **Install wheel** uploads a
package you already downloaded. On **Installed**, summary cards show Installed,
Enabled, Running, and Failed totals; **Search plugins…** filters the installed
list. Use the page controls when the list spans multiple pages.

If the page reports **Plugin manager is unavailable. Repeater is still running**,
the dashboard can reach Repeater but not its separate plugin manager. Skip to
[Manager unavailable](#manager-unavailable); repeatedly clicking Install will
not repair that service.

## Install from the catalogue

1. Select **Catalogue**.
2. Browse the cards. Each identifies the plugin, describes its purpose, and shows
   the repository and available version. Use **Homepage**, when provided, to
   read setup requirements before installing.
3. Click **Install** on the chosen card.
4. Watch the **Installing** dialog. It shows progress output and changes to
   **Complete** or **Error**. **Close** is unavailable while the operation is
   running; wait for its result rather than submitting another install.
5. Once complete, close the dialog and open **Installed**. Confirm the plugin's
   name, version, type, and state.
6. Continue with [Configure a plugin](#configure-a-plugin), then check that its
   application or external connection actually works.

**Catalogue installation enables the plugin immediately.** A service may start
before you configure it. If it must not connect or perform work yet, click
**Disable** in its installed row while you complete setup.

The catalogue offers approved releases, not every release published on GitHub.
Already-installed entries without an available update are hidden from the
catalogue list; find them on **Installed** instead. **All catalogue plugins are
already installed** does not mean your installed list is empty.

If catalogue loading fails, click **Retry** or its own **Refresh** button later.
Installed plugins are unaffected by a catalogue outage. A successful catalogue
checksum check verifies the plugin wheel, not all dependencies it may download.

## Install a downloaded wheel

Use this when a trusted publisher supplies a `.whl` package outside the catalogue,
or when testing your own plugin.

1. Download the plugin's wheel to the computer running your browser. It must be
   compatible with the Repeater host's Python version and platform.
2. Click **Install wheel** at the top of Plugins.
3. In **Install plugin wheel**, choose the `.whl` file and check the selected
   filename. A source ZIP is not a plugin wheel.
4. Click **Install** and wait for the success message or error. This upload uses
   the install dialog, not the catalogue's live progress display.
5. Find the plugin on **Installed**, open **Config**, and review its settings.
6. Click **Enable** when ready.

A **new wheel installation starts disabled**, unlike a catalogue installation.
For a replacement wheel, disable the existing service first, install the reviewed
replacement, then enable it again. Back up its data before replacing it. Uploading
a local wheel does not automatically make it eligible for catalogue updates.

## Configure a plugin

1. On **Installed**, find the plugin and click its **gear icon**, whose tooltip
   is **Config**.
2. The **Config · plugin name** dialog shows a JSON editor and the configuration
   file path. Read the plugin's Homepage/README for what each key means.
3. Edit the required values without removing unrelated settings. This editor
   saves the **whole JSON object**, not just changed keys. Keep quoted property
   names, valid commas, and the surrounding braces.
4. For a service, review **Restart plugin after save**. It is selected by default
   for service plugins; leave it selected to restart an enabled service with the
   new settings. Saving a disabled plugin does not enable it.
5. Click **Save**. Look for the saved confirmation; if a restart was requested,
   verify the service returns to **RUNNING**.
6. Reopen **Config** to check saved values and use **Logs** to check connections.
   If the plugin is disabled, click **Enable** when ready.

**Reset to defaults** replaces the editor contents with the plugin's declared
defaults. It does not save until you click **Save**, and is unavailable when the
plugin declares no defaults. **Cancel** leaves an unsaved edit unapplied.

The **Showing plugin default settings** notice means you are editing a template;
review and save it. An update does not automatically replace existing settings
with new defaults. The manager checks that settings are a JSON object, but the
plugin decides whether its hostnames, ports, credentials, and other values work.

For a bridge plugin, configure its required services separately. For example, a
Companion-based bridge needs a reachable Companion frame server. In Docker,
`127.0.0.1` means the same container—not a service running on the Docker host.
Do not put plugin settings into Repeater's YAML just because both have a Config
page.

:::note[Saved does not always mean restarted]
If an error says configuration was saved but restart failed, the file has
already changed. Reopen Config and inspect Logs before retrying. Do not discard
working settings just to clear the error.
:::

## Open a plugin application

On **Installed**, a plugin with a **UI app** type shows an **Open UI** action
when enabled. Click its **external-link icon** to open the application in a new
tab. If the action is missing, check whether the plugin is enabled and actually
includes a UI; a Service-only plugin has no application page to open.

An enabled UI-only plugin shows **UI READY** and **No background service**. That
is healthy—it does not need a running Python process. A combined service/UI
plugin also needs its background service and required connections to work.

Enabled UI assets are public browser content at your Repeater's origin. API
requests still require authentication. Do not place secrets in application assets
or treat a plugin UI as isolated from other same-origin browser code.

## Understand status and controls

The installed table shows version, state, and whether the plugin is a Service,
UI app, or both. Some actions are icon-only: on desktop, hover to see their
tooltip. On a narrow screen, scroll the installed table horizontally to reach
**Actions**.

| Action | How to recognize it | What it does |
| --- | --- | --- |
| **Enable / Disable** | Labelled power button | Enable starts a service and exposes its UI. Disable stops the service and hides its UI without uninstalling it. |
| **Start** | Play triangle; tooltip Start | Starts an enabled service that is stopped. |
| **Stop** | Square; tooltip Stop | Stops the service for now but leaves it enabled; it can start again when the manager restarts. Its UI remains enabled. |
| **Restart** | Circular arrow; tooltip Restart | Stops and starts an enabled service. |
| **Config** | Gear | Opens the settings editor. |
| **Logs** | Scroll/document icon | Opens recent service output. |
| **Open UI** | External-link icon | Opens an enabled application in a new tab. |
| **Uninstall** | Trash icon | Opens the removal confirmation. |

Use **Disable**, not just Stop, when you want a plugin to stay off after a reboot.
Start, Stop, and Restart are shown for enabled service plugins, not UI-only apps.

| State | Meaning and next step |
| --- | --- |
| **DISABLED** | Installed but switched off. Review Config, then Enable if wanted. |
| **RUNNING** | The service process is running. Check Logs or the application to verify its connection and useful work. |
| **UI READY** | Enabled UI-only application. Use Open UI; no background process is required. |
| **STARTING / STOPPING** | A lifecycle transition. Wait, then Refresh if needed. |
| **STOPPED** | A service is not running. If enabled and expected to run, inspect Logs and use Start. |
| **FAILED** | The service failed or reached its crash-loop limit. Inspect Logs and correct the cause before restarting. |

The **Running** summary counts running processes, so it need not equal
**Enabled** when UI-only apps are installed.

## View logs and diagnose a problem

Click **Logs** in the plugin's row. The dialog shows recent output; click its
**Refresh** button to fetch newer lines, or **Close** to return. It is not a
continuous live log stream. **No log lines yet** can be normal before a service
starts or for a UI-only application.

For a failed service, check for invalid settings, unavailable Companion/API or
upstream services, and missing dependencies. Correct the cause, then use
**Restart** for an enabled service or **Enable** for a disabled one. Five
unexpected exits within sixty seconds stop automatic restarts and leave FAILED.
A service reporting RUNNING can still be disconnected from its upstream service.

Logs and Config can contain credentials. Redact them before sharing screenshots
or support reports. Keep useful logs outside the dialog if you need a lasting
record; captured output is bounded.

## Update a plugin

1. Back up the plugin's persistent data using its publisher's backup guidance.
   The Plugins page does not provide a data export or rollback button.
2. Open **Catalogue** and click its **Refresh** button.
3. Find the installed plugin's card with **Update available**, compare the
   installed and latest versions, and read any upgrade instructions via
   **Homepage**.
4. Click **Update** on that catalogue card. The installed list also shows update
   badges/version hints, but use the catalogue card for the update action.
5. Watch the **Updating** dialog until **Complete**, then close it.
6. Return to **Installed** and verify the new version, enabled state, logs, and
   real application behavior.

Updates preserve settings/data and the enabled flag. Enabled services are
stopped and restarted during the update. A failed update does not guarantee an
automatic rollback or restart of the old service.

If an operation times out or reports an **unknown outcome**, do not immediately
click Install or Update again. It may still finish. Use Refresh, check the
installed version/state and logs, then decide whether another attempt is needed.
Closing a browser tab or losing progress output is not cancellation.

## Uninstall without losing settings

1. On **Installed**, click the plugin's **trash icon** (**Uninstall**).
2. Confirm the plugin name in **Uninstall plugin**.
3. Leave **Also delete persistent data directory** unchecked to keep settings
   and data for a later reinstall. Default removal also retains plugin logs.
4. Click **Uninstall**, then verify the plugin disappears from Installed.

To deliberately remove its persistent data too, back it up first and select
**Also delete persistent data directory** before confirming. **Cancel** closes
the dialog without removing the plugin.

Uninstalling one plugin is different from uninstalling Repeater: removing the
whole Repeater data directory or its container volume can delete every plugin's
data. Removing a plugin also does not undo changes it made outside its own
managed directory.

## Manager unavailable

If Plugins reports that the manager is unavailable, normal Repeater operation
can continue. This is a host/service issue, not a reason to reflash your modem
or repeatedly restart the radio.

- **Native Linux:** older installs need the updated administrator-run managed
  upgrade to provision the manager and refresh the privileged updater helper.
  See [native upgrade instructions](/projects/openhop-repeater/installation/#upgrading-a-native-installation).
- **Docker or Unraid:** update/recreate the intended image while retaining its
  volumes. Check container logs and whether manager startup was deliberately
  disabled. See [Docker](/projects/openhop-repeater/docker/#plugin-manager) or
  [Unraid](/projects/openhop-unraid/installation/#application-plugins-on-plugin-capable-images).
- **Home Assistant add-on:** update the add-on wrapper as well as its packaged
  Repeater. Older wrappers did not start the manager. See
  [add-on troubleshooting](/projects/openhop-ha-addon/installation/#plugin-manager-startup-and-upgrades).

Do not run the plugin manager as root just to bypass permissions. For socket,
startup switches, storage, and service diagnostics, use the
[advanced administration guide](/projects/openhop-repeater/plugin-administration/).

## Further reference

- [Advanced Plugin Administration](/projects/openhop-repeater/plugin-administration/): host setup, API automation, storage, backups, and recovery.
- [Plugin Development](/projects/openhop-repeater/plugin-development/): create and package a service or application.
- [Security and Authentication](/projects/openhop-repeater/security-and-authentication/): access and credential boundaries.
- [Dashboard implementation](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/views/Plugins.vue): source for the controls described here.
