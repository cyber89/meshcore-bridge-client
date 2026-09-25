"""
Raw Serial Framing Adapter (SOF/EOF/ESC and CRC) for MeshCore Bridge.
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


class RawSerialFramingAdapter(BaseSerialAdapter):
    """
    Adaptador determinista basado en pyserial-asyncio con de-framing continuo
    (SOF 0xAA, EOF 0x55, ESC 0x1B, CRC-16 CCITT).
    """

    def __init__(self, port: str, baud_rate: int = 115200, timeout_sec: float = 30.0) -> None:
        super().__init__(port, baud_rate, timeout_sec)
        self._rx_buffer = bytearray()
        self._in_escape = False
        self._in_frame = False

    async def connect(self) -> bool:
        logging.info(f"Iniciando adaptador Serial Raw en {self.port}...")
        self.is_connected = True
        self.heartbeat()
        return True

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
                    self._rx_buffer.append(b ^ ESC_MASK)
                    self._in_escape = False
                elif b == ESC_BYTE:
                    self._in_escape = True
                elif b == EOF_BYTE:
                    self._in_frame = False
                    if len(self._rx_buffer) >= 11:  # Min header (9) + CRC (2)
                        try:
                            frame = MeshcoreFrame.parse_raw_packet(bytes(self._rx_buffer), strict=True)
                            frames.append(frame)
                            if self.rx_callback:
                                self.rx_callback(frame)
                        except Exception as e:
                            logging.warning(f"Error parseando trama raw (frame rechazado): {e}")
                    self._rx_buffer.clear()
                elif b == SOF_BYTE:
                    # Nuevo SOF inesperado: reiniciar buffer
                    self._rx_buffer.clear()
                    self._in_escape = False
                else:
                    self._rx_buffer.append(b)
                    if len(self._rx_buffer) > 512:
                        # Protección anti-desbordamiento
                        self._in_frame = False
                        self._rx_buffer.clear()

        return frames

    async def send_message(
        self,
        text: str,
        target: str | None = None,
        channel_idx: int = 0,
    ) -> dict[str, Any]:
        return {"status": "SENT_RAW", "text": text}

    async def send_admin_cmd(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SENT_ADMIN_RAW", "action": action}
