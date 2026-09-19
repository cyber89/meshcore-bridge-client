from datetime import datetime

from pydantic import BaseModel, Field


class NeighborObservationResponse(BaseModel):
    observer_repeater_id: str
    observer_node_name: str
    pubkey: str
    node_name: str | None = None
    is_repeater: bool | None = None
    contact_type: str | None = None
    route_type: int | None = None
    zero_hop: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    rssi: float | None = None
    snr: float | None = None
    first_seen: datetime | None = None
    last_seen: datetime
    advert_count: int | None = None


class NeighborObservationListResponse(BaseModel):
    hours: int
    total: int
    limit: int
    offset: int
    unique_observed_nodes: int
    unique_observers: int
    items: list[NeighborObservationResponse] = Field(default_factory=list)


class NodeObserverSnapshotResponse(BaseModel):
    observer_repeater_id: str
    observer_node_name: str
    contact_type: str | None = None
    route_type: int | None = None
    zero_hop: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    rssi: float | None = None
    snr: float | None = None
    first_seen: datetime | None = None
    last_seen: datetime
    advert_count: int | None = None


class NodeDetailResponse(BaseModel):
    pubkey: str
    node_name: str | None = None
    is_repeater: bool | None = None
    contact_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    first_seen: datetime | None = None
    last_seen: datetime
    observer_count: int
    zero_hop_observer_count: int
    observers: list[NodeObserverSnapshotResponse] = Field(default_factory=list)


class TopologySummaryResponse(BaseModel):
    hours: int
    total_observations: int
    unique_nodes: int
    unique_observers: int
    zero_hop_observations: int
    multi_hop_observations: int
    stale_nodes: int
    avg_rssi: float | None = None
    avg_snr: float | None = None
    topology_advert_lag_seconds: int | None = None
    mqtt_overall_lag_seconds: int | None = None
    mqtt_packet_lag_seconds: int | None = None
    mqtt_event_lag_seconds: int | None = None
    telemetry_lag_seconds: int | None = None
    top_observer_node_name: str | None = None
    top_observer_count: int | None = None

class TopologyRepeaterTrafficShareResponse(BaseModel):
    repeater_id: str
    repeater_node_name: str
    packet_count: int
    share_percent: float


class TopologySignalDistributionBinResponse(BaseModel):
    range_start: float
    range_end: float
    count: int


class TopologySignalTrendPointResponse(BaseModel):
    bucket_start: datetime
    packet_count: int
    avg_rssi: float | None = None
    avg_snr: float | None = None


class TopologyPacketQualityResponse(BaseModel):
    hours: int
    bucket_minutes: int
    total_packets: int
    avg_rssi: float | None = None
    avg_snr: float | None = None
    route_mix: dict[str, int] = Field(default_factory=dict)
    packet_type_mix: dict[str, int] = Field(default_factory=dict)
    repeater_traffic_share: list[TopologyRepeaterTrafficShareResponse] = Field(default_factory=list)
    rssi_distribution: list[TopologySignalDistributionBinResponse] = Field(default_factory=list)
    snr_distribution: list[TopologySignalDistributionBinResponse] = Field(default_factory=list)
    signal_trend: list[TopologySignalTrendPointResponse] = Field(default_factory=list)


class TopologyPacketSubpathResponse(BaseModel):
    hops: list[str] = Field(default_factory=list)
    count: int


class TopologyPacketGraphNodeResponse(BaseModel):
    node_id: str
    label: str
    count: int


class TopologyPacketGraphEdgeResponse(BaseModel):
    source_node_id: str
    target_node_id: str
    count: int


class TopologyPacketStructureResponse(BaseModel):
    hours: int
    total_packet_events: int
    analyzed_events: int
    packets_with_raw: int
    packets_with_structured_hops: int
    packets_with_decoded_hops: int
    packets_with_channel_details: int
    decode_coverage_percent: float
    channel_detail_mix: dict[str, int] = Field(default_factory=dict)
    top_subpaths: list[TopologyPacketSubpathResponse] = Field(default_factory=list)
    neighbor_graph_nodes: list[TopologyPacketGraphNodeResponse] = Field(default_factory=list)
    neighbor_graph_edges: list[TopologyPacketGraphEdgeResponse] = Field(default_factory=list)


class TopologyEdgeResponse(BaseModel):
    observer_repeater_id: str
    observer_node_name: str
    observer_latitude: float | None = None
    observer_longitude: float | None = None
    observed_node_pubkey: str
    observed_node_name: str | None = None
    observed_latitude: float | None = None
    observed_longitude: float | None = None
    route_type: int | None = None
    zero_hop: bool | None = None
    contact_type: str | None = None
    rssi: float | None = None
    snr: float | None = None
    last_seen: datetime


class TopologyEdgeListResponse(BaseModel):
    hours: int
    total: int
    limit: int
    offset: int
    items: list[TopologyEdgeResponse] = Field(default_factory=list)


class NodeTimeseriesPointResponse(BaseModel):
    bucket_start: datetime
    sample_count: int
    avg_rssi: float | None = None
    avg_snr: float | None = None
    zero_hop_count: int
    route_counts: dict[str, int] = Field(default_factory=dict)


class NodeTimeseriesResponse(BaseModel):
    pubkey: str
    hours: int
    bucket_hours: int
    points: list[NodeTimeseriesPointResponse] = Field(default_factory=list)
