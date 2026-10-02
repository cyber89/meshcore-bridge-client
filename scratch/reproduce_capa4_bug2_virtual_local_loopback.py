"""
Reproducción Bug C4-02: En VirtualMeshAdapter.send_message(), la verificación de la estación base
local solo compara igualdad estricta con la clave de 64 caracteres ('target_clean == local_key').
Un mensaje enviado hacia el prefijo de 12 caracteres de la estación base host omite la guarda,
instancia un nodo sintético y dispara un bucle de eco hacia el bridge (violación de Regla 1.1 Item 2).
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.virtual_mesh_adapter import VirtualMeshAdapter


async def main() -> None:
    print("=== TEST REPRODUCCIÓN BUG C4-02: Omisión de guarda de nodo local en VirtualMeshAdapter ===")

    adapter = VirtualMeshAdapter()
    await adapter.connect()

    events_received = []
    adapter.set_rx_callback(lambda ev: events_received.append(ev))

    local_pubkey = adapter.mc.self_info.get("public_key", "")
    prefix = local_pubkey[:12]  # "112233445566"

    print(f"Clave pública de la estación base local: {local_pubkey}")
    print(f"Prefijo destino probado (12 caracteres):  {prefix}")

    res = await adapter.send_message("Mensaje de prueba hacia prefijo local", target=prefix)
    print(f"\nRespuesta inmediata de send_message: {res}")

    # Esperar el eco simulado
    await asyncio.sleep(0.6)

    print(f"Eventos recibidos en callback RX tras el envío: {len(events_received)}")
    for ev in events_received:
        print(f"  - Evento: {ev.get('type')}, Emisor: {ev.get('sender')}, Texto: {ev.get('text', '')}")

    has_local_echo = any(ev.get("sender") == prefix for ev in events_received)
    status_ok = res.get("status") == "ok"

    print(f"\n¿send_message aceptó el envío (status == 'ok')?: {status_ok}")
    print(f"¿Se generó eco/bucle desde el propio nodo local?: {has_local_echo}")

    await adapter.disconnect()

    if status_ok and has_local_echo:
        print("\n>>> ERROR REPRODUCIDO CON ÉXITO: Bucle local permitido hacia el prefijo de la estación base.")
    else:
        print("\n>>> No se reprodujo el error esperado.")


if __name__ == "__main__":
    asyncio.run(main())
