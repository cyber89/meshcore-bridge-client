---
title: Host Access and Storage
description: Hardware access, networking, and storage behavior for the openHop HA Add-on.
sidebar:
  order: 4
---

The add-on is intentionally permissive because the repeater may need SPI, GPIO, USB, serial, and host-network access depending on the chosen backend.

## Runtime flags

The current add-on manifests use:

- `host_network: true`
- `full_access: true`
- `apparmor: false`

This is deliberate so the repeater can reach local radios, CH341 adapters, serial modems, and companion TCP ports.

## GPIO and SPI on Raspberry Pi hosts

If you are using local Pi-attached radio hardware, enable the required host interfaces in Home Assistant OS before starting the add-on.

On the `hassos-boot` partition:

- add `dtparam=spi=on` to `config.txt`
- add `dtparam=i2c_arm=on` and `dtparam=i2c_vc=on` only if you also need I2C sensors
- create `CONFIG/modules/rpi-i2c.conf` containing `i2c-dev` only if you need I2C

When using local GPIO or SPI:

- disable add-on `Protection mode`
- keep the add-on on hardware-capable hosts such as Raspberry Pi
- use BCM numbering in `config.yaml`

## Storage paths

The add-on maps:

- `addon_config` -> `/config`
- `data` -> `/var/lib/openhop_repeater`

That means:

- main config file: `/config/config.yaml`
- node identity file: `/config/identity.key`
- runtime state: `/var/lib/openhop_repeater`
- upstream runtime config path: `/etc/openhop_repeater/config.yaml`, through a
  symlink to `/config`

With a plugin-capable Repeater image, the default application-plugin root is
`/var/lib/openhop_repeater/plugins` when `storage.storage_dir` uses the mapped
runtime directory. Installed releases, plugin state, plugin data, and logs live
under that root and must be included in backups. A custom `plugins.root` (or
compatibility `plugins.plugins_dir`) outside a persistent mount will not survive
container replacement.

Plugin-manager communication uses a local Unix socket; it does not require a new
host TCP port. Do not expose that socket or enable extra host access just to fix
an unavailable manager. Application plugins run code with the container's access,
so the add-on's broad privileges also apply to the plugin trust decision.

## Network behavior

The repeater web UI binds to port `8000` on the Home Assistant host.

Host networking also matters for:

- companion TCP listeners
- any room-server ports
- `modem_tcp` modem reachability
- broker and control-plane connectivity

Because both channel add-ons use host networking and default to the same ports,
do not run Dev and Main simultaneously without changing all conflicting web,
companion, and room-server listeners.

## Security boundary

`full_access: true`, disabled AppArmor, host networking, and direct hardware
access give this add-on substantially more host reach than a typical add-on. Use
only trusted images and configs, keep the dashboard on a trusted LAN/VPN, and do
not expose hardware devices or port 8000 more broadly than required.

## Related pages

- [Installation](/projects/openhop-ha-addon/installation/)
- [Configuration](/projects/openhop-ha-addon/configuration/)
- [openHop Repeater Hardware Setup](/projects/openhop-repeater/hardware-setup/)
