---
title: Actions and Advanced Services
description: Advanced Home Assistant service actions exposed by the integration.
sidebar:
  order: 6
---

The integration exposes advanced service actions under the `pymc_repeater` domain.

Home Assistant labels these as actions. The compatibility service domain remains
`pymc_repeater`; preserving it keeps existing automations working.

## Radio, room, and database actions

- `ping_neighbor`
- `room_post_message`
- `room_messages_clear`
- `db_purge`
- `update_radio_config`
- `update_mqtt_config`
- `send_advert`
- `publish_neighbors` (schedule an MQTT neighbor-publication cycle)

## CAD calibration actions

- `cad_calibration_start`
- `cad_calibration_stop`
- `cad_manual_check`
- `save_cad_settings`

## Companion actions

- `companion_send_text`
- `companion_send_channel_message`
- `companion_login`
- `companion_request_status`
- `companion_request_telemetry`
- `companion_send_command`
- `companion_reset_path`
- `companion_set_advert_name`
- `companion_set_advert_location`

## Drill-down actions with response data

- `get_broker_presets`
- `get_logs`
- `get_recent_packets`
- `get_filtered_packets`
- `get_packet_by_hash`
- `get_neighbor_links`
- `get_neighbor_link_history`
- `get_neighbor_scopes` (read stored scopes)
- `query_neighbor_scopes` (query one zero-hop neighbor over RF)
- `get_adverts_by_contact_type`
- `get_adverts_count_by_contact_type`
- `get_acl_clients`
- `remove_acl_client`
- `get_room_messages`
- `get_room_clients`
- `delete_room_message`

## Current response and targeting options

- `companion_request_status` and `companion_request_telemetry` accept optional
  `response_variable` support. Calls without a requested response still work.
  Returned backend dictionaries are unwrapped; other result shapes are wrapped
  under `result`. Results do not enter normal polling or entity attributes.
- `get_neighbor_link_history` accepts optional integer `bucket_seconds`, minimum
  60. Omit it for the legacy raw `rows` response. Include it for `buckets`,
  `bucket_seconds`, and bucket `count`; `limit` then caps buckets. The backend
  must support bucketed history: there is no silent fallback to raw rows.
- The raw `update_radio_config` payload supports `radio_id` for multi-radio
  targeting and `direct_advert_interval_hours`. `update_mqtt_config` accepts the
  backend's custom `base_topic` and neighbor-publisher settings.
- Ping reply waits are bounded to 1–60 seconds; companion status/telemetry waits
  to 1–120 seconds. HTTP budgets include a finite margin beyond the RF wait.
  Explicit companion `sent: false` is surfaced as an action error, even inside a
  successful response envelope; older responses omitting `sent` remain supported.

Use **Developer tools → Actions** for required identifiers and current schemas.
This tracks integration dev
[`fc60f15` action registration](https://github.com/openhop-dev/openHop-HA-Integration/blob/fc60f15aed1473a65a0f4363cdb85b7c670736e8/custom_components/pymc_repeater/__init__.py)
and [HTTP client](https://github.com/openhop-dev/openHop-HA-Integration/blob/fc60f15aed1473a65a0f4363cdb85b7c670736e8/custom_components/pymc_repeater/api.py).

## Multi-repeater setups

If you have more than one openHop Repeater config entry in Home Assistant, use `config_entry_id` when calling actions so the integration knows which repeater to target.

## Response and safety notes

Actions that return histories or diagnostics place their payload in the action
response. Use Home Assistant's action-response support when calling them from a
script or automation.

Some actions transmit RF, change radio/MQTT settings, alter CAD calibration,
remove ACL/message data, purge databases, or install updates. Treat them as live
administrative operations—not harmless connectivity tests. Review the action's
current fields in **Developer tools → Actions** before calling it.

## Related

- [Setup in Home Assistant](/projects/openhop-ha-integration/setup-in-home-assistant/)
