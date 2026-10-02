"""
Reproducción Bug C4-03: En VirtualMeshAdapter.send_raw_companion_frame(), el comando
CMD_GET_CHANNEL (0x1F / 31) ejecuta 'bytes.fromhex(secret)' sin verificar si la PSK
almacenada es una cadena hexadecimal válida o una frase de paso ASCII (e.g. 'passphrase12345').
Esto provoca una excepción no controlada ValueError, rompiendo la transacción TCP Companion.
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.virtual_mesh_adapter import VirtualMeshAdapter


async def main() -> None:
    print("=== TEST REPRODUCCIÓN BUG C4-03: Crash por PSK no hexadecimal en VirtualMeshAdapter ===")

    adapter = VirtualMeshAdapter()
    await adapter.connect()

    # 1. Configurar un canal con una contraseña en texto plano (común en despliegues)
    channel_idx = 1
    channel_name = "Operaciones"
    channel_psk = "ClaveSecretaTact"  # 16 caracteres ASCII no hexadecimales

    print(f"Configurando canal {channel_idx} con PSK ASCII: '{channel_psk}'...")
    await adapter.set_channel(channel_idx, channel_name, channel_psk)

    # 2. Cliente TCP Companion consulta la info del canal 1 (Comando 31 / 0x1F)
    # Trama Companion: byte 0 = 31 (CMD_GET_CHANNEL), byte 1 = channel_idx (1)
    query_cmd = bytes([31, channel_idx])

    print(f"Enviando trama binaria Companion CMD_GET_CHANNEL (0x1F 0x{channel_idx:02X})...")

    crashed = False
    exception_type = None
    error_msg = ""

    try:
        res = await adapter.send_raw_companion_frame(query_cmd)
        print(f"Comando ejecutado con éxito: {res}")
    except Exception as e:
        crashed = True
        exception_type = type(e)
        error_msg = str(e)
        print(f"\n¡CRASH DETECTADO! Tipo: {exception_type.__name__}, Mensaje: {error_msg}")
    finally:
        await adapter.disconnect()

    print(f"\n¿Se produjo crash con ValueError?: {crashed and exception_type is ValueError}")

    if crashed and exception_type is ValueError:
        print("\n>>> ERROR REPRODUCIDO CON ÉXITO: bytes.fromhex() no maneja PSKs no hexadecimales en el simulador.")
    else:
        print("\n>>> No se reprodujo el error esperado.")


if __name__ == "__main__":
    asyncio.run(main())
