"""
Reproducción Bug C4-01: MeshcoreSDKAdapter.remove_contact() falla con prefijos de clave
(ej. 12 caracteres hex) por falta de resolución con _resolve_target(), generando
ValueError en meshcore_py y abortando la eliminación en transceptor y caché.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.serial.sdk_adapter import MeshcoreSDKAdapter
from meshcore.commands.contact import ContactCommands


async def main() -> None:
    print("=== TEST REPRODUCCIÓN BUG C4-01: remove_contact con prefijo ===")

    adapter = MeshcoreSDKAdapter(port="COM1")
    adapter.is_connected = True

    full_pubkey = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
    prefix = full_pubkey[:12]  # "a1b2c3d4e5f6"

    # Mock de SDK MeshCore con ContactCommands
    class MockMC:
        def __init__(self):
            self.commands = ContactCommands(None)
            self.commands.send = self.mock_send
            self._contacts = {full_pubkey: {"name": "NodeAlpha", "public_key": full_pubkey}}

        async def mock_send(self, data, *args, **kwargs):
            mock_evt = MagicMock()
            mock_evt.type = "OK"
            mock_evt.payload = {}
            return mock_evt

        def get_contact_by_key_prefix(self, pref):
            for k, v in self._contacts.items():
                if k.startswith(pref):
                    return v
            return None

    adapter.mc = MockMC()

    print(f"Contacto en caché antes del borrado: {list(adapter.mc._contacts.keys())}")
    print(f"Intentando eliminar usando prefijo de 12 caracteres: '{prefix}'...")

    result = await adapter.remove_contact(prefix)

    print(f"Resultado devuelto por adapter.remove_contact: {result}")
    
    # Verificaciones del fallo
    is_error = result.get("status") == "ERROR"
    key_still_present = full_pubkey in adapter.mc._contacts

    print(f"\n¿Fallo con status ERROR?: {is_error}")
    print(f"¿Clave completa sigue presente en mc._contacts?: {key_still_present}")

    if is_error and key_still_present:
        print("\n>>> ERROR REPRODUCIDO CON ÉXITO: remove_contact no resuelve el prefijo a clave completa de 32 bytes.")
    else:
        print("\n>>> No se reprodujo el error esperado.")


if __name__ == "__main__":
    asyncio.run(main())
