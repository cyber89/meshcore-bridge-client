---
title: Performance Tuning
description: Tune Repeater metrics, storage, packet behavior, and radio settings using measured results.
sidebar:
  order: 16
---

Tune from measurements, not from a copied config. Save a baseline, change one
setting at a time, and observe the dashboard and logs over comparable traffic.

## Start with the safe controls

- Keep logging at `INFO` for normal service; use `DEBUG` briefly.
- Increase `send_advert_interval_hours` if the node advertises more often than the
  deployment needs.
- Use `storage.retention.sqlite_cleanup_days` to bound history.
- Set `metrics.rrd_enabled: false` when RRD is unavailable or unwanted; chart
  APIs can fall back to SQLite data.
- Disable unused sensors, GPS sources, MQTT brokers, Glass, room servers, and
  companion identities.
- Disable `sensors.auto_install_packages` on controlled systems.
- Disable unused external plugins separately; sensor package auto-install and the
  plugin manager are different systems. Plugin installs/venv rebuilds can consume
  CPU, disk, and network bandwidth, so schedule them outside RF troubleshooting.

## Packet and mesh controls

- `repeater.cache_ttl` controls duplicate retention; setting it too low can allow
  repeats, while excessive values retain more entries.
- `repeater.max_flood_hops` limits how far already-traversed floods may continue.
- `repeater.use_score_for_tx` shortens eligible transmission delays according to
  packet score; it does not filter or reject packets.
- `repeater.multi_acks` adds redundant ACK airtime and should be enabled only
  when measured reliability justifies it.
- advert rate limits and penalty controls can reduce abusive advert bursts.
- neighbor link metrics are observation-only today; tuning their EWMA and
  retention does not change routes or forwarding.

## Radio tuning

Bandwidth, spreading factor, coding rate, preamble, power, CAD, and LBT trade
range, robustness, latency, and airtime. The values must remain compatible with
the mesh. Do not increase power as the first response to packet loss; inspect
antenna, placement, noise floor, supply quality, and modulation agreement first.

For a CAD-capable backend, follow [CAD Calibration](/projects/openhop-repeater/cad-calibration/)
after the radio and modulation settings are known to receive normal traffic. A
calibrated clear/busy decision reduces unnecessary LBT backoff without making
the radio ignore real compatible channel activity.

Flood/direct delay factors under `delays` are airtime multipliers, not seconds:
the pre-transmit delay is randomized from zero to five times packet airtime times
the configured factor. For KISS, also inspect firmware key-up and CSMA delays;
see [KISS timing](/projects/openhop-repeater/kiss-setup/#optional-kiss-timing).
Do not disable carrier sensing or legal duty-cycle controls simply to reduce delay.

## Storage and charts

Repeater serializes blocking storage work through a dedicated writer. Avoid
editing or vacuuming the live database by hand. Back up state and stop the service
before offline database maintenance. If charts are missing, check the API's
reported `rrd_enabled`, `rrd_available`, and `metrics_data_source` values before
assuming data was lost.

The RF health charts can include or hide packet drop-reason series. That toggle
changes chart presentation only; it is not a persisted daemon or packet-policy
setting. For dense noise-floor history, API clients can page with `limit` and a
non-negative `offset` instead of requesting an unbounded result set.

## Measure after each change

Compare:

- received, sent, repeated, duplicate, CRC-error, and dropped packet counts;
- RSSI/SNR and noise-floor trends;
- neighbor observations and staleness;
- airtime and duty-cycle behavior;
- CPU, memory, disk growth, reconnects, and service restarts.

Return to the saved baseline if a change does not improve the target metric. See
[Configuration Reference](/projects/openhop-repeater/config-file/) and
[Troubleshooting](/projects/openhop-repeater/troubleshooting/).
