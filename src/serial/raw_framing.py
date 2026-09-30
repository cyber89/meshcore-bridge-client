"""
Legacy synthetic frame adapter used only by isolated tooling/simulators.

IMPORTANT: 0xAA/0x55/0x1B + CRC-16 is NOT the official MeshCore Companion
USB/TCP framing and is NOT the MeshCore on-air Packet.h layout. Production
connections must use MeshcoreSDKAdapter / the official Companion protocol.
"""

from __future__ import annotations

import logging
from typing import Any

from src.protocol_types import (
    EOF_BYTE,
    ESC_BYTE,
    ESC_MASK,
    SOF_BYTE,
    MeshcoreFrame,
)
from src.serial.serial_base import BaseSerialAdapter

# Header sintético (9) + payload legado (256) + CRC-16 (2) = 267 bytes
MAX_FRAME_SIZE: int = 267


class RawSerialFramingAdapter(BaseSerialAdapter):
    """
    Adaptador de parsing para el formato sintético legado interno
    (SOF 0xAA, EOF 0x55, ESC 0x1B, CRC-16 CCITT).

    No abre un transporte MeshCore real y no debe seleccionarse como fallback
    de producción.
    """

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout_sec: float = 30.0,
        node_registry: Any = None,
    ) -> None:
        super().__init__(port, baud_rate, timeout_sec, node_registry)
        self._rx_buffer = bytearray()
        self._in_escape = False
        self._in_frame = False

    async def connect(self) -> bool:
        logging.error(
            "RawSerialFramingAdapter es sintético/test-only y no implementa "
            "una conexión MeshCore Companion de producción."
        )
        self.is_connected = False
        return False

    async def disconnect(self) -> None:
        self.is_connected = False
        self._rx_buffer.clear()

    def process_incoming_bytes(self, chunk: bytes) -> list[MeshcoreFrame]:
        """Procesa bytes entrantes a través de la máquina de estados de framing."""
        frames: list[MeshcoreFrame] = []
        self.heartbeat()

        for b in chunk:
            if not self._in_frame:
                if b == SOF_BYTE:
                    self._in_frame = True
                    self._in_escape = False
                    self._rx_buffer.clear()
            else:
                if self._in_escape:
                    if b in (SOF_BYTE, EOF_BYTE):
                        # Violación estricta de protocolo: SOF/EOF no pueden escaparse como datos
                        self._in_frame = False
                        self._in_escape = False
                        self._rx_buffer.clear()
                        logging.warning(f"Violación de framing: delimitador 0x{b:02X} tras ESC. Trama abortada.")
                        continue
                    self._rx_buffer.append(b ^ ESC_MASK)
                    self._in_escape = False
                elif b == ESC_BYTE:
                    self._in_escape = True
                    continue
                elif b == EOF_BYTE:
                    self._in_frame = False
                    self._in_escape = False
                    if len(self._rx_buffer) >= 11:  # Min header (9) + CRC (2)
                        try:
                            frame = MeshcoreFrame.parse_raw_packet(bytes(self._rx_buffer), strict=True)
                            frames.append(frame)
                            if self.rx_callback:
                                try:
                                    self.rx_callback(frame)
                                except Exception as e_cb:
                                    logging.error(f"Error en rx_callback de trama raw: {e_cb}", exc_info=True)
                        except Exception as e:
                            logging.warning(f"Error parseando trama raw (frame rechazado): {e}")
                    self._rx_buffer.clear()
                    continue
                elif b == SOF_BYTE:
                    # Nuevo SOF inesperado en medio de trama: reiniciar buffer
                    self._rx_buffer.clear()
                    self._in_escape = False
                    continue
                else:
                    self._rx_buffer.append(b)

                # Protección anti-desbordamiento universal (rama regular y rama escape)
                if len(self._rx_buffer) > MAX_FRAME_SIZE:
                    self._in_frame = False
                    self._in_escape = False
                    self._rx_buffer.clear()
                    logging.warning(f"Desbordamiento de trama raw (> {MAX_FRAME_SIZE} bytes). Trama abortada.")

        return frames

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "RawSerialFramingAdapter no transmite al hardware MeshCore; "
            "use MeshcoreSDKAdapter para producción."
        )
