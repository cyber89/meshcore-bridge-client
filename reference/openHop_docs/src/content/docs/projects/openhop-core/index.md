---
title: openHop Core Overview
description: Python protocol, node, companion, and radio building blocks for MeshCore applications.
sidebar:
  order: 1
---

openHop Core is a Python implementation of the MeshCore protocol. It provides the
wire-format, cryptography, identity, routing, asynchronous node, optional RF
Fabric, companion, and radio layers used by openHop Repeater and other Python
mesh applications.

The library preserves compatibility with MeshCore firmware while supporting more
than direct SPI radios: applications can use SX1262 hardware, KISS serial modems,
and openHop Modems over USB or TCP. A WebSocket implementation also exists but
should be treated as experimental against the current dispatcher contract.

## What this section covers

- Installation and safe lifecycle patterns
- Protocol, node, RF Fabric, companion, and radio architecture
- Practical node usage, current examples, and hardware safety
- Direct SX1262 and KISS modem compatibility
- Public API entry points, development, and tests

## Useful links

- Project repository: [openHop Core](https://github.com/openhop-dev/openhop_core)
- PyPI package: [openhop-core](https://pypi.org/project/openhop-core/)
- [API Reference](/projects/openhop-core/api-reference/)
- [Examples and Hardware Safety](/projects/openhop-core/examples/)
- [Node and Dispatcher API](/projects/openhop-core/node-and-dispatcher-api/)
- [Protocol API](/projects/openhop-core/protocol-api/)

## Next step

Start with [Quick Start](/projects/openhop-core/quick-start/), then read
[Architecture and Transports](/projects/openhop-core/architecture-and-transports/),
[Node Usage](/projects/openhop-core/node-usage/), or
[Companion Applications](/projects/openhop-core/companion-applications/).

For hosted companion clients, continue to
[Companion Frame Server](/projects/openhop-core/companion-frame-server/) and
[Companion Recipes](/projects/openhop-core/companion-recipes/).
