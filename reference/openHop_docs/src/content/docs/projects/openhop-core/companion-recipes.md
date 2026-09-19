---
title: Companion Recipes
description: Apply CompanionRadio and CompanionBridge to chat, gateways, diagnostics, channels, and frame-server integrations.
sidebar:
  order: 11
---

These recipes map the use cases from the legacy Core companion guide onto the current
companion classes. They are architecture patterns, not copy-and-run radio presets.
Initialize and verify a transport first, then apply the lifecycle in
[Companion Applications](/projects/openhop-core/companion-applications/).

## Chat application

Use `CompanionRadio` when the application owns its radio. Register callbacks before
startup, load contacts/channels from application storage, then start the companion.

Typical operations:

- `advertise()` to announce the node;
- `send_text_message()` for direct messages;
- `send_channel_message()` or `send_channel_data()` for channels;
- message/channel callbacks for received traffic and confirmations;
- `sync_next_message()` for queued offline messages.

Persist identity, contacts, channels, preferences, and messages explicitly. The base
stores are in memory and persistence hooks are no-ops until the application implements
them.

### Send results and CLI text

In Core dev, `send_raw_packet(priority, packet_bytes)` returns `SentResult`, not
a boolean. Check `.success`; parse failures use `error="illegal_arg"` and send
failures use `error="send_failed"`.

Both `TXT_TYPE_CLI_DATA` and `TXT_TYPE_CLI_COMMAND` bypass delivery-ACK waiting in
`send_text_message()` and report `expected_ack=0`. Do not wait for a normal text
ACK for a CLI operation. `send_repeater_command()` defaults to `TXT_TYPE_CLI_DATA`
for older repeater compatibility; use its `txt_type=TXT_TYPE_CLI_COMMAND` option
when addressing a newer companion that requires explicit command messages.
Replies still use CLI_DATA. Core delivers incoming CLI_COMMAND text to the
application; it does not execute a local command automatically.

Source: [current send operations](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/companion/base_send.py).

## Sensor or automation gateway

A gateway can use `CompanionRadio` to discover contacts and issue telemetry or binary
requests. Keep polling bounded and asynchronous:

1. maintain an application-owned contact allow-list;
2. schedule requests with per-device timeouts and backoff;
3. correlate responses through companion callbacks/results;
4. persist only the fields required by the application;
5. avoid flooding the mesh with synchronized polling bursts.

Telemetry may contain location or environmental data. Apply retention and access
controls before forwarding it to MQTT, databases, or external APIs.

## Repeater-hosted companion

Use `CompanionBridge` when another service already owns the radio and dispatcher. Feed
received packets into `process_received_packet()` and provide a packet-injection
callback for outbound companion traffic.

Do not create another radio receive loop. The host and bridge must agree on:

- contact/channel stores and identity ownership;
- outbound packet serialization;
- ACK and response callbacks;
- path updates and flood-copy observations;
- host-supported radio/tuning mutations;
- startup and shutdown ordering.

Avoid delivering the same packet through both a dispatcher subscriber and a manual
bridge path; that produces doubled messages and callbacks.

## Companion frame service

Wrap a bridge with `CompanionFrameServer` when standard companion clients need a TCP
frame protocol:

```python
server = CompanionFrameServer(
    bridge,
    companion_hash,
    device_model="openHop-Companion",
    bind_address="127.0.0.1",
    port=5000,
)
await server.start()
```

The frame server accepts one active client and provides no automatic durable storage,
TLS, or user authentication. Read
[Companion Frame Server](/projects/openhop-core/companion-frame-server/) before
binding beyond loopback.

## Network diagnostics

Use path discovery and trace methods through the companion API rather than manually
parsing response packets. Register response callbacks first, keep request tags scoped
to the initiating component, and handle timeouts as normal network outcomes.

Diagnostics transmit mesh traffic. Rate-limit repeated probes, avoid synchronized
fleet-wide tests, and do not present one path observation as a permanent route.

## Group chat and channels

Channels are indexed records with a name and secret. The channel secret is security
material and also participates in channel identification/decryption.

- load channel records before receiving channel traffic;
- avoid logging or embedding real secrets in examples;
- handle channel message and binary-data events separately;
- persist changes after successful updates;
- consider collision handling when looking up channels by a short hash.

Removing a local channel does not revoke data already shared with other members.
Rotate and redistribute secrets when membership changes require it.

## Contacts and paths

The contact store supports lookup, add/update, removal, import/export, transient
contacts, and capacity handling. The path cache records recent advertisement paths.

Application policy should decide:

- which advert types are auto-added;
- maximum hops for automatic additions;
- whether a full store rejects or overwrites entries;
- when learned paths expire or are reset;
- which contacts are persisted.

Transient anonymous-request contacts are intentionally not durable frame-server
contacts.

## Callbacks

Current callback families include:

- direct messages, channel messages, and channel data;
- adverts, node discovery, and contact path changes;
- send confirmation, trace, login, telemetry, status, and binary responses;
- raw data/RX logging;
- contact deletion/capacity and channel updates.

Callbacks can be synchronous or awaitable through the companion callback layer. Keep
them fast, isolate failures, and hand database/network work to bounded queues.
Registration through `add_push_callback(event_name, callback)` is idempotent.
Use `remove_push_callback(event_name, callback)` to retract only subscriptions
owned by the component being stopped. `clear_push_callbacks()` removes every
subscriber, including other applications, SSE streams, or plugins sharing the
companion; reserve it for whole-companion teardown.

Source: [callback ownership](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/companion/base_callbacks.py).

## Preferences, scope, and radio controls

Companion preferences cover advert identity/location, auto-add policy, path hash mode,
flood/default scope, tuning, custom variables, and other device behavior. Some radio
mutations are available only when the selected transport or bridge host supports
them.

Check capability methods before changing frequency, modulation, TX power, or client
repeat behavior. Validate region, hardware, antenna, and mesh compatibility in the
host application.

Companion-originated flood requests, including a forced-flood retry after a
direct-path failure, use the companion's own scope policy. They are not forced
unscoped merely because they are retries; a bridge's host must not overwrite the
companion's resolved region decision.

## Models

The current public data models include:

| Model | Role |
| --- | --- |
| `Contact` | Identity, name/type, paths, timestamps, and routing metadata |
| `Channel` | Indexed channel name and secret |
| `NodePrefs` | Companion configuration/preferences |
| `SentResult` | Success, route mode, expected ACK/tag, and timeout hint |
| `QueuedMessage` | Offline message queue entry |
| `AdvertPath` | Recently observed advertisement path |
| `PacketStats` | Packet counters |
| `MessageEvent`, `ChannelMessageEvent`, `ChannelDataEvent` | Structured callback payloads |

Inspect the pinned
[`models.py`](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/companion/models.py)
for exact fields. Do not serialize object internals as a stable external schema unless
the application owns and versions that schema.

## Related guides

- [Companion Applications](/projects/openhop-core/companion-applications/)
- [Companion Frame Server](/projects/openhop-core/companion-frame-server/)
- [API Reference](/projects/openhop-core/api-reference/#companion-apis)
- [Node Usage](/projects/openhop-core/node-usage/)
- [Protocol API](/projects/openhop-core/protocol-api/)
