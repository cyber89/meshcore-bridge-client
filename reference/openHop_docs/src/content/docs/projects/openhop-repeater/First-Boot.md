---
title: First Boot
description: Verify the service, onboarding, radio state, and security after installing openHop Repeater.
sidebar:
  order: 5
---

Use this checklist before leaving a new repeater unattended or allowing it to
transmit.

## 1. Check the service

```bash
sudo systemctl status openhop-repeater
sudo journalctl -u openhop-repeater -n 100
```

The service should be active without repeated restarts. The log should show the
selected radio backend, loaded identity, HTTP listener, and any optional services.
Resolve device, permission, config, or bind errors before continuing.

Native installs also provision `openhop-plugin-manager`. Check it separately:

```bash
sudo systemctl status openhop-plugin-manager
sudo journalctl -u openhop-plugin-manager -n 50 --no-pager
```

The manager starts by default; `plugins.enabled: false` intentionally skips
startup. A missing/stopped manager leaves Repeater usable but plugin operations
unavailable. For Docker, inspect container logs instead of running systemd inside
the container. Installing a Python package alone does not provision native units
or refresh an older privileged upgrade helper; see
[Installation](/projects/openhop-repeater/installation/#upgrading-a-native-installation).

## 2. Open onboarding

Visit the setup route directly:

```text
http://<repeater-ip>:8000/setup
```

The `/setup` flow collects the repeater name, hardware/preset, radio parameters,
and login password. A fresh install may route you there automatically, but the
explicit URL is useful when onboarding was interrupted. Do not expose port 8000
directly to the public internet.

Change the example/default admin and guest passwords. The service generates a
JWT secret when one is not already configured. Protect
`/etc/openhop_repeater/config.yaml` because it may contain credentials and an
inline identity.

## 3. Confirm the radio backend

Check the top-level `radio_type` in the config:

- `sx1262` for Linux SPI and system GPIO;
- `sx1262_ch341` for CH341 USB-SPI and CH341 GPIO numbers `0-7`;
- `kiss` for a serial KISS modem;
- `modem_usb` or `modem_tcp` for openHop Modem transports;
- `null` for setup, dashboard, API, or companion-only use without RF.

If a nonempty `radios:` list is configured, inspect every entry instead: it builds
the active multi-radio stack. Changing only the top-level `radio_type` to `null`
does not disable those radios. See [Hardware Setup](/projects/openhop-repeater/hardware-setup/#multiple-radios).

For a new or uncertain setup, start in `repeater.mode: no_tx` or use
`radio_type: null`. Before enabling transmit, verify the antenna, board revision,
GPIO domain, RF switch/TCXO requirements, frequency, bandwidth, spreading factor,
coding rate, preamble, sync settings, and legal power limits.

## 4. Verify storage and identity

The default install uses:

- config: `/etc/openhop_repeater/config.yaml`;
- state: `/var/lib/openhop_repeater`;
- application virtual environment: `/opt/openhop_repeater/venv`;
- service: `openhop-repeater`.

If no identity was configured, first startup creates one. Back it up securely
after onboarding. Losing it changes the node's mesh identity; exposing it allows
another system to impersonate the node.

Include plugin state in backups: the default root is
`/var/lib/openhop_repeater/plugins`, including retained wheels, plugin settings,
data, and logs. A custom `plugins.root` needs a separate backup/persistent mount.
Review plugin settings before enabling workloads; separate processes and venvs
are not a filesystem, network, or credential sandbox.

## 5. Watch normal operation

```bash
sudo journalctl -u openhop-repeater -f
```

Confirm the dashboard updates and received traffic appears when the configured
mesh is active. Send a manual advert only after TX settings are verified; it uses
airtime and announces the node to the mesh.

After reception is proven, calibrate a supported radio's Channel Activity
Detection before leaving the node in normal transmit service. Use both a quiet
baseline and known compatible traffic; see [CAD Calibration](/projects/openhop-repeater/cad-calibration/).

## Next steps

- [Web Dashboard](/projects/openhop-repeater/web-dashboard/)
- [CAD Calibration](/projects/openhop-repeater/cad-calibration/)
- [Configuration Reference](/projects/openhop-repeater/config-file/)
- [Identity Management](/projects/openhop-repeater/identity-management/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
