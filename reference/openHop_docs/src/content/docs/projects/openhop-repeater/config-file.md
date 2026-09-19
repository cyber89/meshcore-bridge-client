---
title: Configuration Reference
description: Current config.yaml reference for openHop Repeater.
sidebar:
  order: 9
---

Reference for configuring openHop Repeater using `config.yaml`, installed at
`/etc/openhop_repeater/config.yaml`. The authoritative, commented schema is
`config.yaml.example` in the Repeater repository's `dev` branch, together with
the runtime configuration readers (some optional settings are only defaulted in
code). This page describes the current development implementation.

Use the dashboard/API for normal configuration changes. Back up configuration
and identity/state first, check the save result, and distinguish saved settings
from settings actually applied live. Do not edit the file concurrently with a
dashboard save.

## Table of Contents

- [Repeater](#repeater)
- [Security](#security)
- [Policy](#policy)
- [Metrics](#metrics)
- [GPS](#gps)
- [Sensors](#sensors)
- [Mesh](#mesh)
- [Identities](#identities)
- [Multi-radio and RF Fabric](#multi-radio-and-rf-fabric)
- [Radio Backend Selection](#radio-backend-selection)
- [CH341 USB-SPI](#ch341-usb-spi)
- [Radio Parameters](#radio-parameters)
- [SX1262 Hardware](#sx1262-hardware)
- [Delays](#delays)
- [Duty Cycle](#duty-cycle)
- [Storage](#storage)
- [Plugins](#plugins)
- [MQTT Brokers](#mqtt-brokers)
- [openHop Glass](#openhop-glass)
- [Logging](#logging)
- [HTTP Server](#http-server)
- [Web](#web)
- [Examples](#examples)

## Repeater

Core node identity and daemon behavior.

### `repeater.node_name`

Friendly name shown in logs, adverts, and the web UI.

### `repeater.mode`

Optional TX mode:

- `forward` repeats traffic normally
- `monitor` keeps RX and higher-level services active but disables repeat forwarding
- `no_tx` disables all transmit activity

### `repeater.latitude` / `repeater.longitude`

Manual coordinates used when you are not advertising a live GPS fix.

### `repeater.identity_file`

Path to the local node identity file. Use an absolute path. If omitted and
`identity_key` is absent, Repeater checks the existing system identity and then
the service account's XDG/home location, creating a key if necessary. See
[Identity Management](/projects/openhop-repeater/identity-management/) for the
exact fallback and recovery behavior.

### `repeater.identity_key`

Optional inline private key. If both `identity_key` and `identity_file` are set,
`identity_key` wins. Omit this field entirely to load from a file: even an
explicit `identity_key: null` bypasses the file-loading branch.

### `repeater.owner_info`

Optional owner string returned to clients requesting owner information.

### `repeater.cache_ttl`

How long duplicate packets stay in cache, in seconds.

### `repeater.max_flood_hops`

Maximum number of hops a flood packet may already have taken before this repeater forwards it.

### `repeater.use_score_for_tx`

Shortens transmission delay according to packet score when the initially
calculated delay is at least 50 ms. It does not filter or reject packets.

### `repeater.multi_acks`

Optional MeshCore-compatible routed acknowledgement redundancy. `0` disables it;
`1` sends a MULTIPART-wrapped redundant copy before the normal routed ACK. Leave
it disabled unless the mesh benefits from the additional airtime.

### Neighbour link metrics

`neighbour_link_metrics_enabled` records observation-only upstream link data.
`neighbour_link_ewma_alpha`, `neighbour_link_ttl_seconds`, and
`neighbour_link_max_entries` control smoothing and retention. These metrics do
not currently change forwarding, deduplication, delays, routes, or packet
acceptance.

### `repeater.score_threshold`

Reserved for future use. Present in config, but does not currently change packet handling.

### `repeater.send_advert_interval_hours`

Automatic advert interval in hours. Set `0` to disable automatic adverts.

### `repeater.direct_advert_interval_hours`

Independent periodic direct-advert stream. The default `0` disables it; enabled
values are `1` through `168` hours.

### `repeater.allow_discovery`

Respond automatically to discovery packets.

### `repeater.advert_rate_limit`

Per-pubkey token-bucket limiting for repeated adverts.

Key fields:

- `enabled`
- `bucket_capacity`
- `refill_tokens`
- `refill_interval_seconds`
- `min_interval_seconds`

### `repeater.advert_penalty_box`

Escalating cooldowns for repeated advert limit violations.

Key fields:

- `enabled`
- `violation_threshold`
- `violation_decay_seconds`
- `base_penalty_seconds`
- `penalty_multiplier`
- `max_penalty_seconds`

### `repeater.advert_adaptive`

Scales advert rate limits based on mesh activity.

Key fields:

- `enabled`
- `ewma_alpha`
- `hysteresis_seconds`
- `thresholds.quiet_max`
- `thresholds.normal_max`
- `thresholds.busy_max`

## Security

Authentication settings are nested under `repeater.security`.

### `repeater.security.max_clients`

Maximum number of authenticated clients for the main Repeater identity. The
current default is `5`. Room-server identities have their own
`settings.max_clients` limits and separate ACLs; this is not a global limit
across every hosted identity.

### `repeater.security.admin_password`

Full-access password for the web UI and API.

### `repeater.security.guest_password`

Guest password for MeshCore mesh-client access. It is **not** a dashboard guest
login; the current web login accepts username `admin` and the admin password.

### `repeater.security.allow_read_only`

Allow read-only MeshCore mesh-client access without a password/ACL entry. This
does **not** disable HTTP API authentication or create an anonymous dashboard.

### `repeater.security.jwt_secret`

JWT signing secret. Leave empty to auto-generate.

### `repeater.security.jwt_expiry_minutes`

Lifetime of each JWT in minutes (default `60`). Authenticated clients can refresh
a valid session; expiry is not necessarily a fixed maximum browser-session age.
See [Security and Authentication](/projects/openhop-repeater/security-and-authentication/)
for the distinction between mesh credentials, web sessions, and API tokens.

## Policy

The optional `policy:` block selects the policy-engine configuration file.
Relative paths are resolved from the directory containing `config.yaml`.

```yaml
policy:
  policy_file: "policy.yaml"
```

## Metrics

The `metrics:` block controls historical metrics storage. When `rrd_enabled` is
true, Repeater stores history with RRDtool when it is available. When false,
chart APIs calculate metrics from `repeater.db` instead.

```yaml
metrics:
  rrd_enabled: true
```

## GPS

Local GPS receiver support is configured under `gps:`.

### `gps.enabled`

Turns GPS parsing on and exposes parsed data at `/api/gps`.

### `gps.source`

Source type:

- `serial` for a directly attached receiver
- `file` for a file or sidecar bridge writing NMEA
- `modem_http` for a networked openHop Modem HTTP `/api/stats` GPS payload

### Serial source settings

```yaml
gps:
  source: serial
  device: "/dev/serial0"
  baud_rate: 9600
  read_timeout_seconds: 1.0
  reconnect_interval_seconds: 5.0
```

### File source settings

```yaml
gps:
  source: file
  source_path: "/var/lib/openhop_repeater/gps_nmea.txt"
  poll_interval_seconds: 2.0
```

### Modem HTTP source settings

Use this when a networked openHop Modem exposes parsed GPS data from its HTTP API.

```yaml
gps:
  enabled: true
  source: modem_http
  host: "REPLACE_WITH_MODEM_HOST"
  port: 80
  endpoint: "/api/stats"
  scheme: "http"
  username: "admin"
  password: "REPLACE_WITH_PASSWORD"
  poll_interval_seconds: 2.0
```

Supported values are `modem_http` and the compatibility alias `http`. Prefer
`modem_http` in new configs.

See [openHop Modem Repeater Integration](/projects/openhop-modem/repeater-integration/) for the full RF, sensor, and GPS setup flow.

### Location behavior

These three settings control different things:

- `api_fallback_to_config_location`: what `/api/gps` shows before a fix
- `advertise_gps_location`: whether outgoing repeater adverts use the GPS fix
- `persist_gps_fix_to_config`: whether valid fixes are written back into `repeater.latitude` and `repeater.longitude`

Related keys:

- `persist_gps_fix_interval_seconds`
- `location_precision_digits`
- `stale_after_seconds`
- `retain_sentences`
- `validate_checksum`
- `require_checksum`

### Time sync

When enabled, the daemon can set system time from a valid GPS UTC fix.

Relevant keys:

- `time_sync_enabled`
- `time_sync_interval_seconds`
- `time_sync_min_offset_seconds`
- `time_sync_min_valid_year`

## Sensors

The sensor subsystem polls host or I2C data sources and exposes them under
`/api/stats`. Current MeshCore status replies also use the first valid sensor bus
voltage as battery voltage. Telemetry replies include available INA219-style bus
voltage, current, and power before temperature and humidity channels.

### Top-level controls

```yaml
sensors:
  enabled: true
  poll_interval_seconds: 10.0
  auto_install_packages: true
  definitions: []
```

Key fields:

- `enabled`
- `poll_interval_seconds`
- `auto_install_packages`
- `definitions`

The example enables automatic dependency installation. Disable
`auto_install_packages` globally and on individual definitions for controlled,
offline, or immutable deployments; enabled sensors can otherwise invoke pip.
These in-process sensor modules are distinct from external
[Plugins](#plugins).

### `sensors.definitions`

Each entry defines one sensor instance.

Common keys:

- `type`
- `name`
- `enabled`
- `auto_install_packages`
- `settings`

The current example config includes these sensor types:

- `hardware_stats`
- `ina219`
- `ens210`
- `shtc3`
- `bme280`
- `waveshare_ups_d`
- `waveshare_ups_e`
- `openhop_modem`

Example:

```yaml
sensors:
  enabled: true
  definitions:
    - type: hardware_stats
      name: system-health
      enabled: true
    - type: shtc3
      name: ambient
      enabled: true
      auto_install_packages: false
      settings:
        i2c_address: 0x70
        bus_number: 1
    - type: openhop_modem
      name: modem
      enabled: true
      settings:
        host: "REPLACE_WITH_MODEM_HOST"
        port: 80
        endpoint: "/api/stats"
        scheme: "http"
        username: "admin"
        password: "REPLACE_WITH_PASSWORD"
        poll_interval_seconds: 60.0
        timeout_seconds: 2.0
```

The `openhop_modem` sensor reads modem diagnostics from an openHop Modem HTTP API and exposes them under `/api/stats -> sensors`. It is useful for battery, solar, and modem-visible GPS diagnostics. If you want Repeater's native `/api/gps` endpoint to use the modem's location fix, configure `gps.source: modem_http` as well.

## Mesh

Mesh-wide forwarding and path encoding behavior.

### `mesh.unscoped_flood_allow`

Controls whether unscoped flood traffic is allowed by default.
`mesh.global_flood_allow` remains an accepted legacy alias and must match the
preferred value when both are present.

### `mesh.path_hash_mode`

Path hash width for originated flood packets:

- `0` = 1-byte hashes
- `1` = 2-byte hashes
- `2` = 3-byte hashes

### `mesh.loop_detect`

Loop detection mode:

- `off`
- `minimal`
- `moderate`
- `strict`

### `mesh.default_region`

Optional default transport-key region for locally originated flood adverts and
the default scope of flood replies whose request scope is unknown. A reply to a
matched served region can instead inherit that region. Leave it `null` for no
default scope. See [Transport Keys](/projects/openhop-repeater/transport-keys/)
for public name-derived regions versus private key material.

## Identities

The repeater can host additional logical identities.

### `identities.room_servers`

Room servers act as independent nodes with their own keys, ACLs, and settings.
Use each room server's `settings.max_clients` to set its authenticated-client
limit independently of `repeater.security.max_clients`.

### `identities.companions`

Companions expose the MeshCore frame protocol over TCP. One client connects per companion TCP port.

Key companion settings:

- `node_name`
- `tcp_port`
- `bind_address`
- `tcp_timeout`

For key generation and imports, see [Identity Management](/projects/openhop-repeater/identity-management/).

## Multi-radio and RF Fabric

Leave `radios:` unset to use the legacy top-level single-radio configuration.
When `radios:` is present, each entry requires a unique `id`. Entries inherit the
top-level `radio_type`, `radio:` air settings, and hardware sections unless they
provide replacements. If no top-level `radio_type` exists, every entry must set
one. A section supplied by an entry replaces that complete top-level section for
that radio; nested values are not merged individually.

```yaml
fabric:
  default_radio: local
  tx_mode: bridge  # default | sticky | bridge

radios:
  - id: local
    radio_type: modem_usb
    radio:
      frequency: 869618000
      bandwidth: 62500
      spreading_factor: 8
      coding_rate: 8
      preamble_length: 32
    modem_usb:
      port: "/dev/openhop-modem"
  - id: link
    radio_type: modem_tcp
    radio:
      frequency: 864200000
      bandwidth: 62500
      spreading_factor: 11
      coding_rate: 8
      preamble_length: 32
    modem_tcp:
      host: "REPLACE_WITH_MODEM_HOST"
      port: 5055
```

`fabric.tx_mode` selects the default radio, the most recent receive radio
(`sticky`), or the opposite radio (`bridge`). It does not broadcast every packet
through every configured radio.

## Radio Backend Selection

Choose the backend with the top-level `radio_type` key.

Supported values in the current repo:

- `sx1262`
- `sx1262_ch341`
- `kiss`
- `modem_tcp`
- `modem_usb`
- `null`
- `none`

### `radio_type: sx1262`

Use a native Linux SPI device with system GPIO, typically on a Raspberry Pi or similar host.

### `radio_type: sx1262_ch341`

Use a CH341 USB-SPI adapter. In this mode the `sx1262` pin values are CH341 GPIO numbers `0-7`, not BCM GPIO numbers.

### `radio_type: kiss`

Use a serial KISS TNC instead of direct GPIO/SPI radio control.

```yaml
radio_type: kiss

kiss:
  port: "/dev/ttyUSB0"
  baud_rate: 9600
```

See [KISS Setup](/projects/openhop-repeater/kiss-setup/) for the operational flow.

### `radio_type: modem_tcp`

Use an openHop Modem over Wi-Fi or Ethernet.

```yaml
radio_type: modem_tcp

modem_tcp:
  host: "REPLACE_WITH_MODEM_HOST"
  port: 5055
  token: ""
  connect_timeout: 5.0
  lbt_enabled: true
  lbt_max_attempts: 5
```

Key fields:

- `host`
- `port`
- `token`
- `connect_timeout`
- `lbt_enabled`
- `lbt_max_attempts`

See [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/) for the operational flow.

### `radio_type: modem_usb`

Use an openHop Modem attached over USB serial.

```yaml
radio_type: modem_usb

modem_usb:
  port: "/dev/ttyACM0"
  baudrate: 921600
  lbt_enabled: true
  lbt_max_attempts: 5
```

Key fields:

- `port`
- `baudrate`
- `lbt_enabled`
- `lbt_max_attempts`

See [openHop USB/TCP Setup](/projects/openhop-repeater/openhop-usb-and-tcp-setup/) for the operational flow.

### `radio_type: null` or `none`

Start the daemon without RF hardware. Use this when you only need dashboard, API, room-server, or companion functionality on the host.

## CH341 USB-SPI

When `radio_type: sx1262_ch341` is selected, configure the adapter under `ch341:`.

```yaml
ch341:
  vid: 6790
  pid: 21778
```

Notes:

- `6790` is `0x1A86`
- `21778` is `0x5512`
- The CH341 requires host USB permissions and is the basis for the current Proxmox LXC flow

## Radio Parameters

These values apply to direct SX1262 hardware and to modem-backed transports unless the modem firmware overrides them.

```yaml
radio:
  frequency: 869618000
  tx_power: 14
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
  preamble_length: 32
  implicit_header: false
```

Important keys:

- `frequency`: in Hz
- `tx_power`: dBm
- `bandwidth`: in Hz
- `spreading_factor`: LoRa SF
- `coding_rate`: LoRa coding rate
- `preamble_length`
- `implicit_header`

## SX1262 Hardware

Direct hardware setup is configured under `sx1262:`.

```yaml
sx1262:
  bus_id: 0
  cs_id: 0
  cs_pin: 21
  reset_pin: 18
  busy_pin: 20
  irq_pin: 16
  txen_pin: -1
  rxen_pin: -1
  en_pin: -1
  txled_pin: -1
  rxled_pin: -1
  use_dio3_tcxo: false
  dio3_tcxo_voltage: 1.8
  use_dio2_rf: false
  is_waveshare: false
```

Notes:

- With `radio_type: sx1262`, pin numbers are BCM GPIO numbers for the host
- With `radio_type: sx1262_ch341`, the same pin fields map to CH341 GPIO numbers
- `use_gpiod_backend` switches GPIO access to libgpiod-backed numbering on platforms such as Luckfox Pico Ultra
- `gpio_chip` selects the gpiod chip index when `use_gpiod_backend` is enabled
- `en_pin` can be used to power-enable some radio boards during initialization
- `use_dio3_tcxo` and `use_dio2_rf` are needed on some E22 and meshadv-class boards

## Delays

Transmission timing multipliers live under `delays:`. They are airtime
multipliers, **not seconds**: the initial randomized TX window is zero through
`5 × packet_airtime × factor`. Scoring and other scheduling controls can further
affect when a queued packet transmits.

```yaml
delays:
  tx_delay_factor: 1.0
  direct_tx_delay_factor: 0.5
  rx_delay_base: 0.0
```

`rx_delay_base` is the separate flood reception-quality delay control. `0.0`
keeps flood processing immediate. It is passed to the Core dispatcher at
startup and applied live when the `delays` section changes. Mesh CLI
`get rxdelay` / `set rxdelay` uses this same setting; the setter accepts `0`
through `20`. It is not the TX delay multiplier or a fixed sleep in seconds.

## Duty Cycle

Duty cycle enforcement is configured under `duty_cycle:`.
`max_airtime_per_minute` is measured in **milliseconds per minute**, not seconds.
The example leaves enforcement disabled; operators must still comply with their
local RF regulations.

```yaml
duty_cycle:
  enforcement_enabled: false
  max_airtime_per_minute: 3600
```

## Storage

Persistent local state and retention settings.

```yaml
storage:
  storage_dir: "/var/lib/openhop_repeater"
  retention:
    sqlite_cleanup_days: 31
    companion_events_days: 31
```

`sqlite_cleanup_days` controls packet/history retention. The companion event
journal uses its independent `companion_events_days` retention period.

The daemon stores runtime data under `storage.storage_dir`. The default install
keeps the main config at `/etc/openhop_repeater/config.yaml` and state data under
`/var/lib/openhop_repeater`. The old top-level `storage_dir` form is deprecated.

## Plugins

External application plugins are managed by a separate process, not loaded as
Python extensions into the Repeater daemon. The optional top-level block is:

```yaml
plugins:
  enabled: true
  # root: "/var/lib/openhop_repeater/plugins"
  # socket: "/var/lib/openhop_repeater/plugin-manager.sock"
  # catalogue_url: "https://repeater-plugins.openhop.dev/catalogue.json"
```

- `enabled` defaults to enabled when omitted. Explicit YAML `false` prevents
  manager startup; it is not a live per-plugin stop command. Use the plugin
  dashboard lifecycle controls for individual plugins.
- `root` defaults to `plugins/` under `storage.storage_dir`.
- `socket` defaults to `plugin-manager.sock` under that storage directory.
  Repeater and the manager must resolve the same socket.
- `catalogue_url` overrides the curated catalogue endpoint and must use HTTPS.
  Changing it changes which catalogue authority you trust.
- Compatibility aliases are `plugins_dir`, `socket_path`, and `catalogue`;
  prefer the names above. Use absolute override paths: explicit relative plugin
  root/socket paths resolve from the process working directory.

Plugin application settings live in the plugin's persistent data directory, not
as arbitrary fields in this block. A missing manager causes plugin API requests
to return HTTP `503`; normal Repeater operation does not depend on it. Docker
also supports `OPENHOP_PLUGIN_MANAGER=0` to omit the manager.

Read [Plugins](/projects/openhop-repeater/plugins/) for installation, upgrades,
settings and recovery, and [Plugin Development](/projects/openhop-repeater/plugin-development/)
for the package contract. Plugins and their dependencies are trusted code, not
sandboxed applications.

## MQTT Brokers

Current repeater builds use `mqtt_brokers:` rather than the older single `mqtt:` block.

```yaml
mqtt_brokers:
  iata_code: "Test"
  status_interval: 300
  owner: ""
  email: ""
  brokers: []
```

Each broker entry supports fields such as:

- `preset`
- `enabled`
- `name`
- `host`
- `port`
- `transport`
- `audience`
- `use_jwt_auth`
- `username`
- `password`
- `format`
- `base_topic` (optional custom root; blank persists as `null` so defaults apply)
- `retain_status`
- `neighbors`
- `tls.enabled`
- `tls.insecure`
- `disallowed_packet_types`

This is also where current LetsMesh-style publishing is modeled.

When `base_topic` is omitted, the `mqtt` format derives
`meshcore/repeater/<node_name>`. MC2MQTT-family formats derive
`meshcore/<iata_code>/<public_key>`.

### Periodic neighbour publication

The development branch can publish a zero-hop neighbour and region-scope table
to the MC2MQTT `neighbors` topic. It is opt-in per broker because some brokers
reject unknown topics and close the connection.

```yaml
mqtt_brokers:
  neighbors:
    enabled: true
    interval_hours: 24
    discovery_timeout_seconds: 60
    scope_response_timeout_seconds: 0
    max_neighbors: 32
    max_neighbor_age_seconds: 86400
    max_sweep_seconds: 900
    duty_cycle_abort_seconds: 30
  brokers:
    - preset: meshat-se
      neighbors: true
```

Important behavior:

- `mqtt_brokers.neighbors` is a settings block, not a boolean. A scalar such as
  `mqtt_brokers.neighbors: true` is ignored with a startup warning.
- `mqtt_brokers.neighbors.enabled` is the master kill switch and defaults to
  `true`; at least one enabled broker must also set `neighbors: true`.
- `interval_hours` accepts `12` through `336` hours.
- Each cycle sends one zero-hop discovery broadcast, then queries neighbour
  scopes serially to avoid response collisions. It can take several minutes and
  consumes RF airtime.
- A value of `0` for `scope_response_timeout_seconds` derives the response window
  from the active radio settings.
- The Meshat.se preset opts in by default. Do not enable the topic for another
  broker until its contract is known to accept it.

See [LetsMesh Integration](/projects/openhop-repeater/letsmesh-integration/) for
manual triggers, status, and the related API endpoints.

## openHop Glass

Central control-plane integration is configured under `glass:`.

```yaml
glass:
  enabled: false
  base_url: "http://localhost:8080"
  inform_interval_seconds: 30
  request_timeout_seconds: 10
  verify_tls: true
  api_token: ""
  cert_store_dir: "/etc/openhop_repeater/glass"
```

Use this when the repeater should post `/inform` payloads to openHop Glass and accept managed updates from it.

## Logging

```yaml
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## HTTP Server

The `http:` block controls the embedded dashboard and API listener. These settings
have supported live-update paths.

```yaml
http:
  enabled: true
  host: "0.0.0.0"
  port: 8000
  thread_pool: 8
  thread_pool_max: 16
  socket_timeout: 65
  socket_queue_size: 100
```

- `enabled` starts or stops the listener.
- `host` and `port` select the bind address and port.
- `thread_pool` and `thread_pool_max` tune CherryPy workers.
- `socket_timeout` and `socket_queue_size` tune idle sockets and the pending
  connection backlog.

Binding to `0.0.0.0` exposes the service on every host interface. Keep it on a
trusted LAN/VPN or protect it with an authenticated reverse proxy.

## Web

Frontend and browser cross-origin settings are configured under `web:`. Listener
address, port, and worker settings belong under `http:`, not `web:`.

```yaml
web:
  cors_enabled: false
  site_name: ""
  # web_path: null
```

Key fields:

- `cors_enabled`
- `site_name`: optional browser UI display name.
- `web_path`: optional alternate frontend selection/path.

The current standalone RepeaterUI uses keyless maps: OpenStreetMap raster tiles
in light mode and OpenFreeMap dark vector tiles in dark mode, with raster
fallback if vector rendering fails. The backend still preserves
`web.carto_api_key` for compatibility with older frontends, but the current UI
does not use or offer that setting. Map tiles are fetched by the browser from
external providers; an offline Repeater does not imply offline basemaps.

## Examples

### Basic SX1262 host

```yaml
radio_type: sx1262

repeater:
  node_name: "mesh-repeater-01"
  latitude: 40.7128
  longitude: -74.0060

mesh:
  unscoped_flood_allow: true
  path_hash_mode: 0
  loop_detect: minimal

radio:
  frequency: 915000000
  tx_power: 20
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8

sx1262:
  cs_pin: 21
  reset_pin: 18
  busy_pin: 20
  irq_pin: 16
```

### KISS modem host

```yaml
radio_type: kiss

repeater:
  node_name: "kiss-repeater"

kiss:
  port: "/dev/ttyUSB0"
  baud_rate: 9600

radio:
  frequency: 915000000
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
```

### openHop USB modem host

```yaml
radio_type: modem_usb

repeater:
  node_name: "usb-modem-repeater"

modem_usb:
  port: "/dev/ttyACM0"
  baudrate: 921600
  lbt_enabled: true
  lbt_max_attempts: 5

radio:
  frequency: 915000000
  tx_power: 14
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
  preamble_length: 32
```

### openHop TCP modem host

```yaml
radio_type: modem_tcp

repeater:
  node_name: "tcp-modem-repeater"

modem_tcp:
  host: "REPLACE_WITH_MODEM_HOST"
  port: 5055
  token: ""
  connect_timeout: 5.0
  lbt_enabled: true
  lbt_max_attempts: 5

radio:
  frequency: 915000000
  tx_power: 14
  bandwidth: 62500
  spreading_factor: 8
  coding_rate: 8
  preamble_length: 32
```

### CH341 / Proxmox-style host

```yaml
radio_type: sx1262_ch341

ch341:
  vid: 6790
  pid: 21778

sx1262:
  cs_pin: 0
  rxen_pin: 1
  reset_pin: 2
  busy_pin: 4
  irq_pin: 6
  use_dio3_tcxo: true
  use_dio2_rf: true
```

## Notes

- The current repo schema is defined by the upstream `config.yaml.example` in `openhop_repeater`.
- Older repeater docs and examples may still mention a top-level `mqtt:` block;
  use `mqtt_brokers:` instead. `mesh.global_flood_allow` remains a legacy alias
  for `mesh.unscoped_flood_allow`, not the preferred name.
- Some HTTP, logging, and radio parameters can be applied live, while
  `radio_type`, KISS transport, and modem transport changes require a restart.
- After restart-required edits, run `sudo systemctl restart openhop-repeater` and
  watch logs with `journalctl -u openhop-repeater -f`.
- Legacy `/etc/pymc_repeater` and `/var/lib/pymc_repeater` installations are
  migrated by the current management script; new documentation and installs use
  the openHop paths.

## Implementation references

- [Commented configuration](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/config.yaml.example)
- [Plugin path and catalogue defaults](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/repeater/plugins/storage.py)
- [Live-update regression coverage](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/tests/test_flood_rx_delay_wiring.py)
- [RepeaterUI navigation](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/config/navigation.ts)
- [Keyless map implementation](https://github.com/openhop-dev/openHop_RepeaterUI/blob/f1a5fb5/src/utils/mapTiles.ts)
