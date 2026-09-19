---
title: Entities and Controls
description: Overview of the monitoring and control entities exposed by the integration.
sidebar:
  order: 4
---

The integration exposes both monitoring entities and control entities.

## Monitoring

Examples of included telemetry:

- repeater version and update status
- uptime, memory use, database size, metrics history size
- packet totals, RX and forwarded rates, airtime, RSSI, SNR, CRC errors
- MQTT handler status and one binary sensor per broker
- ACL totals and companion state
- room statistics
- GPS diagnostics when available from the repeater API
- external sensor-manager data, including supported modem and UPS readings
- neighbor-link counts and current default-region state
- aggregate radio status/problem state, distinct from API connectivity
- application-plugin counts and individual plugin health
- source age/staleness and component endpoint diagnostics
- parent flood/direct RX, TX, and duplicate totals since process startup

## Control entities

Examples of included controls:

- buttons:
  - send advert
  - restart repeater service
  - vacuum metrics database
  - check for updates
  - install latest update
- select:
  - repeater mode
  - update channel
- switches:
  - duty cycle enforcement
  - advert rate limit
  - advert penalty box
  - advert adaptive control
  - allow unscoped flood
- numbers:
  - max airtime percent
  - advert tuning and rate-limit values

CAD calibration and manual CAD checks are response-returning actions rather than
ordinary entities. Neighbor histories, broker presets, packet/contact drill-downs,
and other large datasets are also fetched on demand so they do not inflate every
poll.

## Application-plugin health

The shared poll reads the lightweight `/api/plugins/` inventory. Installed,
enabled, running, and failed counts are separate from external sensor-manager
readings. Per-plugin entities expose version, state, enabled, running, and problem
status, identified by stable plugin IDs. Paths, settings, logs, PIDs, and
repository metadata are not retained as entity telemetry.

An empty inventory is zero; an unavailable, unsupported, or malformed inventory
is unknown, not a healthy empty installation. Enabled UI-only plugins do not
need a running process. The failed count uses explicit `FAILED`; an individual
enabled runtime plugin in `FAILED` or `STOPPED` indicates a problem, while
`STARTING` or unrecognized state remains unknown. These controls are read-only:
installing, enabling, removing, or configuring plugins remains a Repeater task.

## Radio child devices

Radio inventory is discovered on shared polls. Child devices expose read-only
configured frequency, bandwidth, TX power, spreading factor, coding rate, and
preamble where supplied. They do not inherit the parent's packet totals, RSSI,
noise, CRC, or connection health. Configuration is not proof of applied RF
settings or measured per-radio traffic.

After two distinct successful full polls confirm absence from a valid radio
inventory, the integration disables the missing child device rather than deleting
it. Custom names, registry IDs, and history are retained. Returning canonical
identities restore integration-disabled devices; user-disabled choices remain
unchanged. Malformed, ambiguous, or empty inventories and GPS-only notifications
do not retire devices. Permanent removal is only allowed for confirmed absent
radio children and loses registry identity if they are added again.

Use [radio ID aliases](/projects/openhop-ha-integration/setup-in-home-assistant/#preserve-radio-identities)
when changing a backend ID, rather than relying on display-name matching.

## Sensor freshness and battery trends

Source measurements become unavailable when failed, stale, missing, or of unknown
freshness. Freshness prefers the reading envelope's effective
`poll_interval_seconds`; the legacy global-summary fallback is used only when
that field is absent, never when present but invalid. An integration update alone
cannot establish the effective cadence of an older backend's sensor plugin.

Signed `solar_charge_rate_percent_per_hour` remains `%/h`, not electrical current
or power. With a fresh successful reading, its sign gives charging, discharging,
or neutral trend. Neutral does not mean a full battery.

## Native update entity

**Repeater software** reads cached update status. Before a successful version
check, latest version remains unknown instead of claiming the installation is
up to date. Installation is explicit, on the selected Repeater channel, and only
allowed for a confirmed available update without a status error. Version
selection and backup requests are unsupported. The entity does not automatically
install or switch channels, and it does not replace HA add-on or Unraid container
image updates.

## Other dynamic entities

Some entities are created from live repeater data at setup time, including:

- MQTT brokers
- companions
- room servers
- route types
- database table counters

Reload the integration if changes to these setup-time entities do not appear.
Radio, application-plugin, and external sensor discovery also run on subsequent
coordinator updates; they do not all require a reload.

Source: integration dev
[`fc60f15` operational contracts](https://github.com/openhop-dev/openHop-HA-Integration/blob/fc60f15aed1473a65a0f4363cdb85b7c670736e8/docs/operational-monitoring.md)
and [native update implementation](https://github.com/openhop-dev/openHop-HA-Integration/blob/fc60f15aed1473a65a0f4363cdb85b7c670736e8/custom_components/pymc_repeater/update.py).

## Related

- [Dashboard Template](/projects/openhop-ha-integration/dashboard-template/)
- [Actions and Advanced Services](/projects/openhop-ha-integration/actions-and-advanced-services/)
