---
title: Companion Frame Server
description: Expose a CompanionBridge through the MeshCore TCP frame protocol with explicit lifecycle, persistence, and network boundaries.
sidebar:
  order: 10
---

`CompanionFrameServer` exposes a companion implementation to standard MeshCore
companion clients over TCP. It wraps an existing `CompanionBridge`; it does not create
or own a second radio.

This guide tracks openHop Core `dev` commit
[`68272ce`](https://github.com/openhop-dev/openhop_core/tree/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/companion/frame_server).

## When to use it

Use a frame server when a host application already owns the dispatcher/radio and a
companion client needs the MeshCore binary frame interface. openHop Repeater uses this
pattern to provide virtual companion identities.

Do not use it as an unauthenticated public Internet API. The base frame transport does
not add TLS, user authentication, authorization, rate limiting, or durable storage.
Place it behind the network controls appropriate to the deployment.

## Ownership model

| Component | Owns |
| --- | --- |
| Host application | Radio, dispatcher, service lifecycle, durable configuration |
| `CompanionBridge` | Companion state and packet injection into the host dispatcher |
| `CompanionFrameServer` | TCP listener, one active client, frame parsing/writing, command dispatch, push notifications |
| Subclass/application | Persistence hooks, battery/storage reporting, local telemetry, access controls |

## Construction and lifecycle

```python
from openhop_core.companion import CompanionFrameServer

server = CompanionFrameServer(
    bridge=bridge,
    companion_hash="f5",
    device_model="openHop-Companion",
    bind_address="127.0.0.1",
    port=5000,
)

await server.start()
try:
    # Host application work.
    ...
finally:
    await server.stop()
```

The default bind address in the current constructor is `0.0.0.0`. Bind to loopback or
a specific private interface unless broader exposure is intentional and protected.
The default port is 5000, but each server on one host needs a unique listening port.

The server accepts one active client. A new connection evicts the previous client.
The default idle read timeout is eight hours; set it explicitly to fit the host's
connection policy or to `None` only when indefinite idle connections are intended.

## Frame transport

Inbound and outbound frames use separate one-byte prefixes, a little-endian two-byte
payload length, and the payload:

```text
prefix | payload_length_u16_le | payload
```

The server rejects frames larger than the current maximum. Invalid prefixes are
logged and skipped. The writer uses one bounded queue and one writer task so command
responses, pushes, and heartbeat frames cannot write concurrently to the socket.

When the outbound queue is full or a payload is too large, the frame is dropped and a
warning is logged. This is deliberate backpressure shedding, not durable delivery.
Applications that require guaranteed delivery must implement persistence and client
reconciliation above the transport.

A current-time heartbeat is emitted when no queued frame is available within the
configured heartbeat interval. Socket keepalive and `TCP_NODELAY` are enabled where
the host platform supports them.

## Command families

The current command registry covers:

- application start and device query;
- contacts: list, lookup, add/update, remove, reset path, import/export/share;
- channels: get and set;
- direct text, channel text/data, raw data, and raw packet sends;
- offline message synchronization;
- repeater login, logout, status, telemetry, and connection status;
- binary, anonymous, path-discovery, control, and trace requests;
- self advert, name, location, time, radio parameters, TX power, and tuning;
- flood/default scope and path-hash mode;
- identity import/export and incremental signing;
- statistics, battery/storage, custom variables, auto-add, and allowed repeat
  frequencies.

Exact command constants and payload encodings are defined in the pinned
[`companion constants`](https://github.com/openhop-dev/openhop_core/blob/68272cec2a1312de92c7ec0df529b195d4563575/src/openhop_core/companion/constants.py)
and command modules. Treat those bytes as a protocol contract; do not derive wire
formats from this prose alone.

Unsupported commands return the protocol's unsupported-command error. Malformed
arguments and handler exceptions return an illegal-argument error rather than
terminating the server.

## Push notifications

The server subscribes to bridge callbacks and pushes relevant events to the connected
client, including:

- direct and channel messages/data;
- send confirmations;
- adverts, discovered nodes, contact/path changes, and contact-capacity events;
- binary and path-discovery responses;
- trace, raw RX, and control data.

Host code can also push trace or raw receive data through the synchronous scheduling
helpers or their asynchronous counterparts. Avoid pushing the same packet through
both host and bridge paths; doubled input becomes doubled client output.

Frame-server reconnect and shutdown remove only the frame server's own bridge
subscriptions. Other application or plugin subscribers remain registered. If
your host also uses companion push callbacks, remove its callbacks individually
rather than calling the companion-wide `clear_push_callbacks()` during a client
disconnect.

## Persistence hooks

The base implementation uses in-memory companion stores. These methods are hooks, not
durable storage by default:

- persist/pop companion messages;
- persist one contact or save the full contact list;
- save channels;
- save/load preferences in the companion layer;
- report battery/storage and local telemetry.

A subclass should perform small, bounded operations and avoid blocking the event loop.
Transient anonymous contacts are deliberately excluded from contact persistence.
Protect private keys, channel secrets, login material, and message contents according
to the host application's threat model.

## Radio mutation boundary

Frame commands can request radio parameters, TX power, repeat settings, and tuning.
The bridge reports whether the host supports each mutation. A host that cannot safely
apply a setting must reject it rather than pretending success.

Validate allowed frequencies, maximum power, board/front-end limits, and regional
rules in the host application. A binary command protocol is not a regulatory policy
engine.

## Network and operational safety

Before exposing a listener:

1. Choose the bind address and firewall scope deliberately.
2. Confirm whether the surrounding service provides authentication or encrypted
   transport.
3. Use a unique companion identity/hash and port.
4. Set an idle timeout and connection-monitoring policy.
5. Bound queues and persistence growth.
6. Avoid logging frame payloads that contain identities, secrets, or messages.
7. Verify that a reconnect evicts only the intended previous client.

## Related guides

- [Companion Applications](/projects/openhop-core/companion-applications/)
- [Companion Recipes](/projects/openhop-core/companion-recipes/)
- [API Reference](/projects/openhop-core/api-reference/#companion-apis)
- [Node and Dispatcher API](/projects/openhop-core/node-and-dispatcher-api/)
