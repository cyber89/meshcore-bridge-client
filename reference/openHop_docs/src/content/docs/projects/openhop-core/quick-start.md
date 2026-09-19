---
title: openHop Core Quick Start
description: Install openHop Core safely, choose an application layer, and understand lifecycle ownership before connecting a radio.
sidebar:
  order: 2
---

## Requirements

- Python 3.10 through 3.13
- A virtual environment on modern Debian, Ubuntu, and Raspberry Pi OS systems
- A supported radio backend only when you are ready to receive or transmit

## Install the base library

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
python -m pip install openhop-core
```

The base package is enough for packet, identity, cryptography, and protocol work.
Add only the transport extras you need:

```bash
# Direct SX1262, USB, and serial hardware support
python -m pip install "openhop-core[hardware]"

# WebSocket radio support
python -m pip install "openhop-core[websocket]"
```

For a source checkout, clone the repository and install its development tools in
the active virtual environment:

```bash
git clone https://github.com/openhop-dev/openhop_core.git
cd openhop_core
python -m pip install -e ".[dev]"
```

## Verify the installation without a radio

```python
from openhop_core import LocalIdentity, __version__

identity = LocalIdentity()
print(f"openHop Core {__version__}")
print(f"public key length: {len(identity.get_public_key())} bytes")
```

This creates a new in-memory identity. Decide how your application will persist
its private identity before joining a real mesh.

## Choose the application entry point

Most applications should start with `CompanionRadio`. It owns a `MeshNode` and
provides contacts, channels, messaging, advertisements, queues, callbacks,
telemetry, and statistics. Register callbacks before startup, stop the companion
in `finally`, and then close or clean up the selected transport. See
[Companion Applications](/projects/openhop-core/companion-applications/) for a
lifecycle skeleton and persistence cautions.

Use `CompanionBridge` when a host such as Repeater already owns the radio and node.
Use direct `MeshNode` only for lower-level dispatcher/transport integrations.

## Understand the lower-level node lifecycle

`MeshNode.start()` runs until another task stops the node. Do not await it inline
and expect the statements after it to run. Once a radio object has been created
and initialized for your hardware, use this lifecycle shape:

```python
import asyncio

from openhop_core import LocalIdentity, MeshNode


async def run(radio) -> None:
    identity = LocalIdentity()
    node = MeshNode(radio=radio, local_identity=identity)
    node_task = asyncio.create_task(node.start())

    try:
        # Application work goes here while the dispatcher is running.
        await asyncio.Event().wait()
    finally:
        await node.stop()
        await node_task
        # The caller also owns radio shutdown/cleanup.
```

The exact radio constructor, device path, GPIO mapping, modulation, and cleanup
method depend on the selected backend. Confirm regional frequency and power rules,
attach a suitable antenna, and verify wiring before initializing or transmitting.

## Choose the next guide

- [Architecture and Transports](/projects/openhop-core/architecture-and-transports/)
- [Node Usage](/projects/openhop-core/node-usage/)
- [Companion Applications](/projects/openhop-core/companion-applications/)
- [Examples and Hardware Safety](/projects/openhop-core/examples/)
- [Direct SX1262 Hardware Setup](/projects/openhop-core/direct-sx1262-hardware/)
- [Core Development](/projects/openhop-core/development/)
