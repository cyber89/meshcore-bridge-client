---
title: Node Usage
description: Run MeshNode safely, send packets, subscribe to events, and understand dispatcher and handler ownership.
sidebar:
  order: 4
---

`MeshNode` is the low-level openHop Core facade around a radio, local identity,
dispatcher, and optional event service. Use it when an application needs direct
packet and handler control. Most chat, contact, channel, queue, telemetry, and
request/response applications should use
[Companion Applications](/projects/openhop-core/companion-applications/) instead.

This guide tracks openHop Core `dev` commit
[`77f116a`](https://github.com/openhop-dev/openhop_core/tree/77f116a8dab097642d04a16c8aaf097c0dd33cc3).

## Constructor and ownership

```python
MeshNode(
    radio,
    local_identity,
    config=None,
    *,
    contacts=None,
    channel_db=None,
    logger=None,
    event_service=None,
)
```

The node:

- stores the radio and `LocalIdentity` supplied by the caller;
- creates a `Dispatcher` and registers the default packet handlers;
- passes optional contacts, channels, node name, radio configuration, and event
  service into those handlers;
- exposes `send_packet()` as its one transport-level send entry point.

The application owns:

- construction, initialization, and cleanup of the selected radio;
- identity persistence and protection;
- contact and channel persistence;
- application-level message construction and response handling.

## Lifecycle

`MeshNode.start()` enters `Dispatcher.run_forever()` and does not return until
another task stops the node. Start it as a task when the application must continue
running other work.

```python
import asyncio

from openhop_core import LocalIdentity, MeshNode


async def run(radio) -> None:
    node = MeshNode(radio, LocalIdentity())
    node_task = asyncio.create_task(node.start())

    try:
        # Register application work before waiting here.
        await asyncio.Event().wait()
    finally:
        await node.stop()
        await node_task
        # Close or clean up the concrete radio here.
```

`node.stop()` is idempotent, disarms receive handling, and stops the dispatcher. It
does not close the radio and does not cancel every packet task already in flight.
The caller must wait for the node task and then clean up the transport.

Read [Direct SX1262 Hardware](/projects/openhop-core/direct-sx1262-hardware/) or
[KISS Modem Protocol Compatibility](/projects/openhop-core/kiss-modem-protocol/)
before opening hardware.

## Sending packets

`MeshNode.send_packet(packet, *, wait_for_ack=False, **kwargs)` forwards a constructed
packet to the dispatcher. Packet construction belongs to `PacketBuilder` or a
higher-level companion method; avoid assembling wire bytes by hand.

```python
sent = await node.send_packet(packet, wait_for_ack=True)
if not sent:
    # Handle transport failure or acknowledgement timeout.
    ...
```

The dispatcher serializes transmission, and `MeshNode.send_packet()` returns a
boolean. A lower-level radio `send()` may return a metadata mapping, which may be
empty; `None` means transport failure. Custom backends must not return `None` for a
successful write.

Acknowledgements, direct paths, flood routing, timeout selection, airtime budgeting,
and response correlation have protocol-specific rules. Prefer companion methods for
text, channels, adverts, repeater login, status, telemetry, and binary requests.

## Default handlers

The dispatcher registers handlers for the current MeshCore payload families,
including:

- acknowledgements and multipart acknowledgements;
- adverts and contact updates;
- direct text and group/channel messages;
- path and trace responses;
- login and anonymous-request responses;
- protocol requests and responses;
- control and discovery traffic.

Applications can inspect a registered handler with `get_handler_instance()`, add a
handler with `register_handler()`, or add a fallback with
`register_fallback_handler()`. A handler is asynchronous and must not block the event
loop with serial, filesystem, database, or network work.

Do not replace a default handler casually. ACK correlation, decryption, contact path
updates, duplicate handling, and return-path teaching are coupled across several
handlers and dispatcher callbacks.

## Raw packet callbacks

The dispatcher supports packet-sent, packet-received, ACK, enhanced raw-packet, and
raw-RX subscribers. Use these for observation or host integration rather than
building a second receive loop around the same radio.

Callbacks can be synchronous or awaitable where the dispatcher contract permits it.
Keep them fast and hand expensive work to a bounded application queue. Never log
private identity keys or decrypted content merely because a raw callback exposes it.

## Events

Pass an `EventService` to the constructor or call `set_event_service()` after
construction. `set_event_service()` propagates the service to handlers that publish
events.

```python
from openhop_core.node import EventService, EventSubscriber, MeshEvents


class Subscriber(EventSubscriber):
    async def handle_event(self, event_type, data) -> None:
        print(event_type, data)


events = EventService()
subscriber = Subscriber()
events.subscribe(MeshEvents.NEW_MESSAGE, subscriber)

node = MeshNode(
    radio,
    identity,
    event_service=events,
)
```

Current event constants cover new/updated contacts, direct and channel messages,
node discovery, signal updates, node start/stop, and telemetry updates. Event data is
handler-produced application data, not a stable serialized wire format.

`publish_sync()` schedules an asynchronous task and therefore requires a running
event loop. Subscriber exceptions are logged and isolated from other subscribers.
Unsubscribe long-lived objects when their owning component shuts down.

## Contacts and channels

Passing `contacts` lets handlers resolve identities, paths, and shared secrets.
Passing `channel_db` enables channel/group decryption and message handling. These are
application-owned stores; `MeshNode` does not persist them.

For built-in stores, callbacks, queues, path discovery, and higher-level send APIs,
use [Companion Applications](/projects/openhop-core/companion-applications/).

## Configuration boundaries

The optional `config` dictionary currently supplies the node name and radio settings
to default handlers. It does not initialize physical hardware for you. Confirm:

- concrete transport and device path;
- SPI bus/chip select and GPIO numbering;
- TCXO and RF-switch wiring;
- frequency, bandwidth, spreading factor, coding rate, preamble, sync word, and TX
  power;
- antenna, regional rules, and duty-cycle limits.

Do not copy old example pinouts or frequencies as universal defaults.

## Diagnostics and shutdown checklist

Before blaming packet routing:

1. Confirm the radio initialized and receive handling is armed.
2. Confirm the local identity and mesh radio settings match the intended network.
3. Check handler registration and event/callback wiring.
4. Inspect dispatcher filter statistics for duplicate or rejected packets.
5. Verify ACK waits and response callbacks are cleaned up after timeouts.
6. Stop the node, await its task, then close the radio exactly once.

## Related guides

- [Quick Start](/projects/openhop-core/quick-start/)
- [Architecture and Transports](/projects/openhop-core/architecture-and-transports/)
- [Examples and Hardware Safety](/projects/openhop-core/examples/)
- [API Reference](/projects/openhop-core/api-reference/#meshnode)
- [Companion Applications](/projects/openhop-core/companion-applications/)
