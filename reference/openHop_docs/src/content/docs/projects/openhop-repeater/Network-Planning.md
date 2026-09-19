---
title: Network Planning
description: Plan repeater placement, RF settings, airtime, scope, and monitoring before deployment.
sidebar:
  order: 15
---

Good repeater placement is an RF and operations problem, not simply a matter of
adding more transmitters. Start with a receive-only survey and add forwarding
only where it improves paths without creating unnecessary airtime.

## Plan the role

Decide whether the host will be a forwarding repeater, monitor, no-TX observer,
room server, companion endpoint, API/dashboard host, or a combination. Use
`repeater.mode: monitor` to keep receive and higher-level services active without
repeat forwarding, and `no_tx` to disable all transmit activity.

Monitor mode is **not receive-only**: companions and tenants may still transmit.
Use `no_tx` for a survey that must remain silent.

## Match the mesh

All participants must agree on frequency, bandwidth, spreading factor, coding
rate, preamble, sync behavior, and path-hash convention. Use a regional preset as
a starting point, then verify it against the actual mesh and local regulations.
Do not copy example frequencies or power values blindly.

## Placement checklist

- Prefer height and clear line of sight over maximum transmit power.
- Use a band-appropriate antenna, low-loss feed line, weather protection, and a
  stable power supply.
- Keep the radio and feed line away from digital noise sources.
- Confirm enclosure temperature and remote recovery options.
- For TCP modems, plan LAN reachability and failure behavior separately from RF.
- Record the exact board revision, pin map, preset, and antenna used.

## Airtime and loops

Every repeated packet consumes shared airtime. `max_flood_hops`, duplicate cache,
duty-cycle enforcement, path hashes, loop detection, advert intervals, and
optional multi-ACK redundancy all affect network load. Change one control at a
time and compare packet, neighbor, RSSI/SNR, error, and airtime trends.

Transport-key regions can constrain flood scope. They do not create RF isolation:
all transmitters still share the channel.

## Multi-radio backhaul

The optional `radios:` list can join radios with different frequencies or modem
types through RF Fabric. Validate each segment's modulation and legal power
separately. `fabric.tx_mode: bridge` selects a different radio from the last
receiver; with more than two radios it selects the first other entry, not every
interface. With no prior reception it falls back to the default radio.

This is not automatic route selection or independent repeaters per interface.
Plan loops and recovery deliberately, and check the actual RX/TX path under load.
See [Multiple radios](/projects/openhop-repeater/hardware-setup/#multiple-radios).

## Rollout

1. Install with `radio_type: null` or `repeater.mode: no_tx`.
2. Confirm identity, storage, dashboard, and remote access.
3. Initialize the final radio settings in `no_tx` for receive-only monitoring.
4. Compare observed neighbors and noise floor over a representative period.
5. Enable forwarding at legal power and watch airtime and duplicate behavior.
6. Document a rollback path and keep a secure config/identity backup.

See [Hardware Setup](/projects/openhop-repeater/hardware-setup/),
[Performance Tuning](/projects/openhop-repeater/performance-tuning/), and
[Transport Keys](/projects/openhop-repeater/transport-keys/).
