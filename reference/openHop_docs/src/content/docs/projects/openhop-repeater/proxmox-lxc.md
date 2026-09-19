---
title: Proxmox LXC Installation
description: Create and operate a Debian 13 openHop Repeater LXC on Proxmox VE using the current dev installer.
sidebar:
  order: 4.75
---

The current `dev` installer creates a dedicated Debian 13 LXC for openHop
Repeater. It supports CH341 USB-to-SPI radios and openHop Modems connected over
TCP or USB.

Use this when you want an always-on Repeater on a Proxmox host without dedicating
a full virtual machine or Raspberry Pi.

## Requirements

Software:

- Proxmox VE 8.x or 9.x; Proxmox VE 9.x is recommended for new deployments
- a Debian 13 standard LXC template available through `pveam`
- Internet access from the container during installation and updates
- an `amd64` or `arm64` Proxmox host

Choose one radio path:

- CH341 USB-to-SPI adapter with USB VID `1a86` and PID `5512`, wired to a
  compatible SX1262 module
- openHop Modem over TCP, reachable from the LXC network
- openHop Modem over USB, connected to the Proxmox host

## Security and host changes

Run the installer as `root` on the Proxmox host, not inside a container. Review
it before use because it:

- creates a **privileged** LXC with nesting and start-at-boot enabled
- enables general USB-bus passthrough in the LXC configuration
- can install a CH341 udev rule on the Proxmox host
- performs a full Debian package upgrade inside the new container
- enables root auto-login on the Proxmox container console
- installs openHop Repeater and an operator-facing `update` command

The prompted root password protects password-based root login, but the Proxmox
console is configured for root auto-login. Keep Proxmox administration itself
restricted to trusted operators.

## Install the current dev script

Run this on the Proxmox host:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/openhop-dev/openhop_repeater/dev/scripts/proxmox-install.sh)"
```

Do not use `curl ... | bash` for this interactive installer. Its prompts read
from standard input, so piping the script directly into Bash can make the prompts
consume script lines as answers.

The fetched installer defaults to cloning the Repeater `dev` branch. The Git
branch can be changed at its prompt.

## Installer prompts and defaults

| Setting | Default |
| --- | --- |
| Container ID | Next available cluster ID |
| Hostname | `openhop-repeater` |
| RAM | 1024 MB |
| Swap | 512 MB |
| Disk | 4 GB |
| CPU cores | 2 |
| Bridge | `vmbr0` |
| VLAN ID | None |
| Root filesystem storage | `local-lvm` |
| Template storage | `local` |
| Git branch | `dev` |
| Root password | `openHop1!` |
| Host-side CH341 udev rule | No |
| Optional openHop Console WebUI | No |

The installer validates the selected container ID, VLAN, and Git branch, then
shows an effective summary before creating anything. Change the public default
root password during installation.

## What the installer does

After confirmation, the installer:

1. Selects the newest Debian 13 standard template matching the Proxmox host
   architecture and downloads it when needed.
2. Creates a privileged, DHCP-configured LXC with optional VLAN tagging,
   nesting, start-at-boot, and general USB passthrough.
3. Installs the host-side CH341 udev rule only when selected.
4. Starts the LXC and fails if network connectivity does not become ready within
   the bounded retry period.
5. Runs `apt-get update` and `apt-get full-upgrade` inside the LXC, then installs
   locale support, `curl`, Git, and `whiptail`.
6. Clones the selected Repeater branch to `/root/openhop-repeater`.
7. Installs `/usr/local/bin/openhop-update` and the short `update` alias.
8. Pre-seeds `/etc/openhop_repeater/config.yaml` with the CH341/E22 radio mapping.
9. Runs `manage.sh install`, provisioning Repeater and its plugin-manager unit;
   radio onboarding is completed in the browser afterward.
10. Optionally installs openHop Console assets without selecting them as the
    active frontend.
11. Adds Proxmox container notes and prints the dashboard URL.

## Select the radio path

### CH341 and E22-style module

Answer **Yes** to the CH341 udev-rule prompt. The installer pre-seeds these CH341
adapter GPIO numbers:

| Function | CH341 GPIO |
| --- | ---: |
| CS | 0 |
| RXEN | 1 |
| Reset | 2 |
| Busy | 4 |
| IRQ/DIO1 | 6 |

It also enables DIO3 TCXO control and the DIO2 RF switch for the E22-style
profile. These are CH341 adapter GPIO identifiers, not Raspberry Pi BCM numbers.
Verify the exact module wiring, RF-switch design, frequency, regional settings,
antenna, and power limit before transmitting.

### openHop Modem over TCP

Leave the CH341 udev rule disabled. General USB passthrough is still present, but
TCP mode does not use it. During Repeater setup, select `modem_tcp` and enter the
modem's reachable LAN address, TCP port, and token if configured.

### openHop Modem over USB

Leave the CH341 udev rule disabled. The installer passes `/dev/bus/usb`, but that
alone does **not** expose the USB serial `/dev/ttyACM*` or `/dev/ttyUSB*` node.
Configure serial-device passthrough on the Proxmox host for the actual device,
allow its character-device major/minor in the LXC configuration, and verify the
`repeater` user can open its container-side path before selecting `modem_usb`.
See the diagnostic example below; the installer does not add these serial rules.

:::caution
The installer currently pre-seeds the configuration for CH341 regardless of the
selected radio path. TCP and USB modem users must change the backend during the
Repeater setup flow before expecting the radio connection to work.
:::

## Complete first boot

After installation, enter the LXC when needed:

```text
pct enter <CTID>
```

Open the dashboard and complete the setup wizard:

```text
http://<container-ip>:8000
```

Useful management commands inside the LXC:

```bash
journalctl -u openhop-repeater -f
cd /opt/openhop_repeater
bash manage.sh
```

Continue with [First Boot](/projects/openhop-repeater/first-boot/) and verify the
selected radio backend and regional RF settings before enabling transmission.

## Update the LXC

Run this as root inside the container:

```bash
update
```

The helper prints its planned actions and requires a `y/N` confirmation. It then:

- updates installed Debian packages
- requires a clean `/root/openhop-repeater` checkout
- verifies the current branch can fast-forward to its matching remote branch
- pulls with `--ff-only`
- runs `manage.sh upgrade` for that branch
- updates openHop Console when Console assets are installed
- refreshes the installed management and update-helper copies

It aborts instead of discarding local changes, switching a detached checkout, or
merging divergent history.

Back up container config, identities, data, and any custom plugin root before
updating. The current `manage.sh upgrade` also refreshes the privileged OTA helper
and provisions/restarts the plugin manager. Existing hosts need this administrator
upgrade once before relying on the updated dashboard updater. Check
`systemctl status openhop-repeater openhop-plugin-manager` and actual dashboard
readiness afterward; `plugins.enabled: false` intentionally skips the manager.

## Optional openHop Console

When selected, the installer clones the public Console distribution repository to
`/root/pymc_console` and installs its current release assets. It deliberately does
not make Console the active frontend. Complete the standard Repeater setup wizard
first, then select **openHop Console** from Web Settings if wanted.

This LXC script still offers the legacy standalone Console install/update path.
It is separate from the new plugin catalogue and from current Docker images,
which no longer bundle Console. Do not assume an LXC `update` upgrades a
catalogue-installed plugin; manage that plugin through Plugins instead.

## Troubleshooting

### Debian 13 template not found

Refresh the Proxmox template catalog:

```bash
pveam update
```

The installer requires a Debian 13 standard template matching the host's `amd64`
or `arm64` architecture.

### CH341 not found on the host

```bash
lsusb -d 1a86:5512
```

If the rule was selected, verify `/etc/udev/rules.d/99-ch341.rules` and reload the
host rules if necessary:

```bash
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --action=change
```

### USB is unavailable inside the LXC

Verify these lines exist in `/etc/pve/lxc/<CTID>.conf`:

```text
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir 0 0
```

Those lines grant USB-bus access (for example CH341), not serial-device access.
For a USB modem, identify the actual node on the host with `ls -l /dev/ttyACM0`.
If it is specifically `/dev/ttyACM0` with major/minor `166, 0`, a device-specific
configuration example is:

```text
lxc.cgroup2.devices.allow: c 166:0 rwm
lxc.mount.entry: /dev/ttyACM0 dev/ttyACM0 none bind,optional,create=file 0 0
```

Do not copy those numbers for a different node: USB serial drivers can use
different majors/minors. Apply the host configuration in a maintenance window,
restart the LXC, and verify the device and permissions inside it. Recheck after
USB reconnects. Prefer TCP mode when reliable serial passthrough is unavailable.

### Repeater starts with the wrong backend

The installer pre-seeds `sx1262_ch341`. Open the setup/configuration UI and select
`modem_tcp` or `modem_usb` when using an openHop Modem, then restart Repeater.

## Source

- [Current dev installer](https://github.com/openhop-dev/openhop_repeater/blob/dev/scripts/proxmox-install.sh)
- [Current dev README section](https://github.com/openhop-dev/openhop_repeater/tree/dev#proxmox-lxc-installation)
- [LXC update helper](https://github.com/openhop-dev/openhop_repeater/blob/dev/scripts/openhop-update)
