---
title: Setup in Home Assistant
description: Configure the integration from the Home Assistant UI and understand its setup flow.
sidebar:
  order: 3
---

After installation:

1. Open `Settings` -> `Devices & Services`.
2. Click `Add Integration`.
3. Search for `openHop Repeater`.
4. Enter:
   - repeater host or IP
   - repeater API port
   - repeater admin password
5. Submit the form.

## What happens during setup

The integration will:

1. connect to the repeater API
2. sign in as `admin`
3. create a dedicated API token for Home Assistant
4. store the token in the config entry
5. stop using the admin password for normal polling

## Options

The integration options let you change:

- polling interval from 5 to 300 seconds; the default is 15 seconds
- system uptime display unit
- data size display unit
- radio ID aliases (JSON), for explicitly preserving an existing radio identity
  when its backend ID changes

Changing an option reloads the integration automatically. One integration-wide
poll drives the normal entities; GPS updates use a separate server-sent-event
stream when the Repeater exposes it.

With multiple Repeaters, each host and port is a separate config entry. Advanced
actions should include `config_entry_id` so Home Assistant targets the intended
Repeater.

## Update checks

Normal polling reads cached update status; it does not discover GitHub branches
or start a version check on every poll. A separate non-forced check runs at
`HH:01:00` in Home Assistant's configured timezone. It respects Repeater's cache
and rate-limit hold, skips overlapping checks/installations, and does not check
immediately at startup or install anything automatically. The manual **Check for
updates** button still requests a forced check. Channel choices use `main`,
`dev`, and the current channel without querying GitHub for a branch list.

## Preserve radio identities

Home Assistant display names are not radio identities. If you deliberately change
a backend radio ID, use **Radio ID aliases (JSON)** to map the new runtime ID to
the existing HA ID. For example, `{"local": "radio0"}` preserves the old `radio0`
device when the same physical radio is now called `local`. Use `{}` to clear the
mapping. Only map confirmed identities; duplicate targets, chains, cycles, and
simultaneously present source/target IDs are rejected.

The original target ID may return when the alias source is absent, allowing a
single/multi-radio round trip without replacing the HA device. See
[radio lifecycle behavior](/projects/openhop-ha-integration/entities-and-controls/#radio-child-devices)
before permanently removing a device.

## Authentication after a Repeater restart

The integration stores an API token, while Repeater stores its matching hash in
SQLite. Preserve both Repeater's JWT secret and database. In the HA add-on,
`storage.storage_dir` should use the mapped `/var/lib/openhop_repeater` path, not
the legacy unmapped `/var/lib/pymc_repeater`. Lost authentication state can require
reauthentication even when the integration's saved token has not changed.

Source: integration dev
[`fc60f15`](https://github.com/openhop-dev/openHop-HA-Integration/tree/fc60f15aed1473a65a0f4363cdb85b7c670736e8/custom_components/pymc_repeater),
including `coordinator.py` and `config_flow.py`.

## Naming

The integration tries to use the repeater node name from openHop Repeater instead of showing only the host and port.

## Related

- [Entities and Controls](/projects/openhop-ha-integration/entities-and-controls/)
- [Actions and Advanced Services](/projects/openhop-ha-integration/actions-and-advanced-services/)
