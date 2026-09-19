from datetime import datetime

from pydantic import BaseModel


class PacketRecordResponse(BaseModel):
    id: str
    repeater_id: str
    node_name: str
    timestamp: datetime
    packet_type: str | None = None
    route: str | None = None
    rssi: float | None = None
    snr: float | None = None
    src_hash: str | None = None
    dst_hash: str | None = None
    packet_hash: str | None = None
    payload: str | None = None


class PacketSummaryResponse(BaseModel):
    hours: int
    total_packets: int
    unique_repeaters: int
    unique_sources: int
    unique_destinations: int
    avg_rssi: float | None = None
    avg_snr: float | None = None
    by_packet_type: dict[str, int]
    by_route: dict[str, int]
    packets_per_repeater: dict[str, int]
