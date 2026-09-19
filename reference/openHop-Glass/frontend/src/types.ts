export type UserRole = "admin" | "operator" | "viewer" | string;

export interface BootstrapStatusResponse {
  needs_bootstrap: boolean;
  server_setup_complete: boolean;
}

export interface BootstrapAdminRequest {
  email: string;
  password: string;
  display_name?: string;
}

export interface UserInfoResponse {
  id: string;
  email: string;
  role: UserRole;
  display_name: string | null;
}

export interface UserManagementResponse {
  id: string;
  email: string;
  role: UserRole;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserCreateRequest {
  email: string;
  password: string;
  role: UserRole;
  display_name?: string;
  is_active?: boolean;
}

export interface UserUpdateRequest {
  role?: UserRole;
  display_name?: string | null;
  is_active?: boolean;
  password?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: UserInfoResponse;
}

export interface RepeaterResponse {
  id: string;
  node_name: string;
  pubkey: string;
  status: string;
  firmware_version: string | null;
  location: string | null;
  config_hash: string | null;
  last_inform_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepeaterCreateRequest {
  node_name: string;
  pubkey: string;
  status?: string;
  firmware_version?: string;
  location?: string;
}

export interface RepeaterUpdateRequest {
  status?: string;
  firmware_version?: string;
  location?: string;
  config_hash?: string;
}

export interface InformSnapshotPointResponse {
  timestamp: string;
  cpu: number | null;
  memory: number | null;
  disk: number | null;
  uptime_seconds: number | null;
  noise_floor: number | null;
  rx_total: number | null;
  tx_total: number | null;
  forwarded: number | null;
  dropped: number | null;
  airtime_percent: number | null;
}

export interface RepeaterDetailResponse extends RepeaterResponse {
  state: string | null;
  system: Record<string, unknown> | null;
  radio: Record<string, unknown> | null;
  counters: Record<string, unknown> | null;
  settings: Record<string, unknown> | null;
  snapshots: InformSnapshotPointResponse[];
  cert_diagnostics: RepeaterCertDiagnosticLogResponse[];
}

export interface RepeaterCertDiagnosticLogResponse {
  timestamp: string;
  severity: string;
  source: string;
  message: string;
  details: Record<string, unknown>;
}

export interface DeleteStaleRepeatersResponse {
  removed: number;
}

export interface AdoptionActionRequest {
  note?: string;
}

export interface AdoptionActionResponse {
  repeater_id: string;
  node_name: string;
  status: string;
}

export type CommandAction =
  | "restart_service"
  | "config_update"
  | "upgrade_firmware"
  | "set_radio"
  | "set_mode"
  | "send_advert"
  | "rotate_cert"
  | "set_inform_interval"
  | "reboot"
  | "export_config"
  | "export_identity"
  | "run_diagnostic";

export const COMMAND_ACTIONS: CommandAction[] = [
  "restart_service",
  "config_update",
  "upgrade_firmware",
  "set_radio",
  "set_mode",
  "send_advert",
  "rotate_cert",
  "set_inform_interval",
  "reboot",
  "export_config",
  "export_identity",
  "run_diagnostic",
];

export interface QueueCommandRequest {
  node_name: string;
  action: CommandAction;
  params: Record<string, unknown>;
  requested_by: string;
  reason?: string;
}

export interface QueueCommandResponse {
  command_id: string;
  node_name: string;
  action: string;
  status: string;
  queued_at: string;
}

export interface ConfigSnapshotExportRequest {
  repeater_id?: string;
  node_name?: string;
  reason?: string;
}

export interface ConfigSnapshotExportQueuedResponse {
  command_id: string;
  repeater_id: string;
  node_name: string;
  status: string;
  queued_at: string;
}

export interface ConfigSnapshotResponse {
  id: string;
  repeater_id: string;
  node_name: string;
  command_id: string | null;
  captured_at: string;
  created_at: string;
  encryption_key_id: string;
  payload_sha256: string;
  payload_size_bytes: number;
}

export interface ConfigSnapshotDetailResponse extends ConfigSnapshotResponse {
  payload: Record<string, unknown>;
}

export interface CommandQueueItemResponse {
  command_id: string;
  repeater_id: string;
  node_name: string;
  action: string;
  status: string;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  requested_by: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AuditRecordResponse {
  id: string;
  user_id: string | null;
  timestamp: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
}

export interface MqttTelemetryEventResponse {
  event_id: string;
  repeater_id: string;
  node_name: string;
  timestamp: string;
  event_type: string;
  event_name: string | null;
  topic: string;
  payload: Record<string, unknown>;
  ingested_at: string;
}

export interface PacketRecordResponse {
  id: string;
  repeater_id: string;
  node_name: string;
  timestamp: string;
  packet_type: string | null;
  route: string | null;
  rssi: number | null;
  snr: number | null;
  src_hash: string | null;
  dst_hash: string | null;
  packet_hash: string | null;
  payload: string | null;
}

export interface PacketSummaryResponse {
  hours: number;
  total_packets: number;
  unique_repeaters: number;
  unique_sources: number;
  unique_destinations: number;
  avg_rssi: number | null;
  avg_snr: number | null;
  by_packet_type: Record<string, number>;
  by_route: Record<string, number>;
  packets_per_repeater: Record<string, number>;
}

export interface NeighborObservationResponse {
  observer_repeater_id: string;
  observer_node_name: string;
  pubkey: string;
  node_name: string | null;
  is_repeater: boolean | null;
  contact_type: string | null;
  route_type: number | null;
  zero_hop: boolean | null;
  latitude: number | null;
  longitude: number | null;
  rssi: number | null;
  snr: number | null;
  first_seen: string | null;
  last_seen: string;
  advert_count: number | null;
}

export interface NeighborObservationListResponse {
  hours: number;
  total: number;
  limit: number;
  offset: number;
  unique_observed_nodes: number;
  unique_observers: number;
  items: NeighborObservationResponse[];
}

export interface NodeObserverSnapshotResponse {
  observer_repeater_id: string;
  observer_node_name: string;
  contact_type: string | null;
  route_type: number | null;
  zero_hop: boolean | null;
  latitude: number | null;
  longitude: number | null;
  rssi: number | null;
  snr: number | null;
  first_seen: string | null;
  last_seen: string;
  advert_count: number | null;
}

export interface NodeDetailResponse {
  pubkey: string;
  node_name: string | null;
  is_repeater: boolean | null;
  contact_type: string | null;
  latitude: number | null;
  longitude: number | null;
  first_seen: string | null;
  last_seen: string;
  observer_count: number;
  zero_hop_observer_count: number;
  observers: NodeObserverSnapshotResponse[];
}

export interface TopologySummaryResponse {
  hours: number;
  total_observations: number;
  unique_nodes: number;
  unique_observers: number;
  zero_hop_observations: number;
  multi_hop_observations: number;
  stale_nodes: number;
  avg_rssi: number | null;
  avg_snr: number | null;
  topology_advert_lag_seconds: number | null;
  mqtt_overall_lag_seconds: number | null;
  mqtt_packet_lag_seconds: number | null;
  mqtt_event_lag_seconds: number | null;
  telemetry_lag_seconds: number | null;
  top_observer_node_name: string | null;
  top_observer_count: number | null;
}

export interface TopologyEdgeResponse {
  observer_repeater_id: string;
  observer_node_name: string;
  observer_latitude: number | null;
  observer_longitude: number | null;
  observed_node_pubkey: string;
  observed_node_name: string | null;
  observed_latitude: number | null;
  observed_longitude: number | null;
  route_type: number | null;
  zero_hop: boolean | null;
  contact_type: string | null;
  rssi: number | null;
  snr: number | null;
  last_seen: string;
}

export interface TopologyEdgeListResponse {
  hours: number;
  total: number;
  limit: number;
  offset: number;
  items: TopologyEdgeResponse[];
}

export interface NodeTimeseriesPointResponse {
  bucket_start: string;
  sample_count: number;
  avg_rssi: number | null;
  avg_snr: number | null;
  zero_hop_count: number;
  route_counts: Record<string, number>;
}

export interface NodeTimeseriesResponse {
  pubkey: string;
  hours: number;
  bucket_hours: number;
  points: NodeTimeseriesPointResponse[];
}

export interface TopologyRepeaterTrafficShareResponse {
  repeater_id: string;
  repeater_node_name: string;
  packet_count: number;
  share_percent: number;
}

export interface TopologySignalDistributionBinResponse {
  range_start: number;
  range_end: number;
  count: number;
}

export interface TopologySignalTrendPointResponse {
  bucket_start: string;
  packet_count: number;
  avg_rssi: number | null;
  avg_snr: number | null;
}

export interface TopologyPacketQualityResponse {
  hours: number;
  bucket_minutes: number;
  total_packets: number;
  avg_rssi: number | null;
  avg_snr: number | null;
  route_mix: Record<string, number>;
  packet_type_mix: Record<string, number>;
  repeater_traffic_share: TopologyRepeaterTrafficShareResponse[];
  rssi_distribution: TopologySignalDistributionBinResponse[];
  snr_distribution: TopologySignalDistributionBinResponse[];
  signal_trend: TopologySignalTrendPointResponse[];
}

export interface TopologyPacketSubpathResponse {
  hops: string[];
  count: number;
}

export interface TopologyPacketGraphNodeResponse {
  node_id: string;
  label: string;
  count: number;
}

export interface TopologyPacketGraphEdgeResponse {
  source_node_id: string;
  target_node_id: string;
  count: number;
}

export interface TopologyPacketStructureResponse {
  hours: number;
  total_packet_events: number;
  analyzed_events: number;
  packets_with_raw: number;
  packets_with_structured_hops: number;
  packets_with_decoded_hops: number;
  packets_with_channel_details: number;
  decode_coverage_percent: number;
  channel_detail_mix: Record<string, number>;
  top_subpaths: TopologyPacketSubpathResponse[];
  neighbor_graph_nodes: TopologyPacketGraphNodeResponse[];
  neighbor_graph_edges: TopologyPacketGraphEdgeResponse[];
}
export interface AlertLifecycleRequest {
  note?: string;
}

export interface NotificationEventResponse {
  id: string;
  channel: string;
  event_type: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface AlertResponse {
  id: string;
  repeater_id: string | null;
  node_name: string | null;
  timestamp: string;
  alert_type: string;
  severity: string;
  message: string;
  state: string;
  first_seen_at: string;
  last_seen_at: string;
  fingerprint: string | null;
  acked_at: string | null;
  acked_by: string | null;
  note: string | null;
  resolved_at: string | null;
}

export interface AlertDetailResponse extends AlertResponse {
  notifications: NotificationEventResponse[];
}

export interface AlertSummaryResponse {
  total: number;
  active: number;
  acknowledged: number;
  suppressed: number;
  resolved: number;
  by_severity: Record<string, number>;
  by_state: Record<string, number>;
}

export interface NodeGroupCreateRequest {
  name: string;
  description?: string;
}

export interface NodeGroupUpdateRequest {
  name?: string;
  description?: string | null;
}

export interface NodeGroupMemberAddRequest {
  repeater_id: string;
}

export interface NodeGroupMemberResponse {
  repeater_id: string;
  node_name: string;
  status: string;
  last_inform_at: string | null;
}

export interface NodeGroupResponse {
  id: string;
  name: string;
  description: string | null;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface NodeGroupDetailResponse extends NodeGroupResponse {
  members: NodeGroupMemberResponse[];
}
export interface TransportKeyGroupCreateRequest {
  name: string;
  parent_group_id?: string | null;
  flood_policy?: "allow" | "deny";
  transport_key?: string | null;
  sort_order?: number;
}

export interface TransportKeyGroupUpdateRequest {
  name?: string;
  parent_group_id?: string | null;
  flood_policy?: "allow" | "deny";
  transport_key?: string | null;
  sort_order?: number;
}

export interface TransportKeyCreateRequest {
  name: string;
  group_id?: string | null;
  flood_policy?: "allow" | "deny";
  transport_key?: string | null;
  sort_order?: number;
}

export interface TransportKeyUpdateRequest {
  name?: string;
  group_id?: string | null;
  flood_policy?: "allow" | "deny";
  transport_key?: string | null;
  sort_order?: number;
}

export interface TransportKeyGroupResponse {
  id: string;
  name: string;
  parent_group_id: string | null;
  flood_policy: "allow" | "deny" | string;
  transport_key: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface TransportKeyResponse {
  id: string;
  name: string;
  group_id: string | null;
  flood_policy: "allow" | "deny" | string;
  transport_key: string | null;
  sort_order: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TransportKeyTreeNodeResponse {
  id: string;
  kind: "group" | "key" | string;
  name: string;
  flood_policy: "allow" | "deny" | string;
  transport_key: string | null;
  parent_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface TransportKeySyncStatusResponse {
  repeater_id: string;
  node_name: string;
  status: string;
  payload_hash: string | null;
  command_id: string | null;
  error_message: string | null;
  queued_at: string | null;
  dispatched_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
}

export interface TransportKeyTreeResponse {
  nodes: TransportKeyTreeNodeResponse[];
  sync_status: TransportKeySyncStatusResponse[];
}

export interface TransportKeySyncTriggerResponse {
  payload_hash: string;
  queued_commands: number;
  skipped_commands: number;
}

export interface AlertPolicyTemplateCreateRequest {
  name: string;
  description?: string;
  rule_type: string;
  severity: string;
  enabled: boolean;
  threshold_value?: number;
  window_minutes?: number;
  offline_grace_seconds?: number;
  cooldown_seconds?: number;
  auto_resolve?: boolean;
  config?: Record<string, unknown>;
}

export interface AlertPolicyTemplateUpdateRequest {
  name?: string;
  description?: string | null;
  severity?: string;
  enabled?: boolean;
  threshold_value?: number | null;
  window_minutes?: number | null;
  offline_grace_seconds?: number | null;
  cooldown_seconds?: number;
  auto_resolve?: boolean;
  config?: Record<string, unknown> | null;
}

export interface AlertPolicyTemplateResponse {
  id: string;
  name: string;
  description: string | null;
  rule_type: string;
  severity: string;
  enabled: boolean;
  threshold_value: number | null;
  window_minutes: number | null;
  offline_grace_seconds: number | null;
  cooldown_seconds: number;
  auto_resolve: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AlertPolicyAssignmentCreateRequest {
  template_id: string;
  scope_type: string;
  scope_id?: string;
  priority?: number;
  enabled?: boolean;
}

export interface AlertPolicyAssignmentUpdateRequest {
  priority?: number;
  enabled?: boolean;
}

export interface AlertPolicyAssignmentResponse {
  id: string;
  template_id: string;
  template_name: string;
  rule_type: string;
  scope_type: string;
  scope_id: string | null;
  scope_name: string | null;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface EffectivePolicyItemResponse {
  rule_type: string;
  template_id: string;
  template_name: string;
  severity: string;
  threshold_value: number | null;
  window_minutes: number | null;
  offline_grace_seconds: number | null;
  cooldown_seconds: number;
  auto_resolve: boolean;
  config: Record<string, unknown>;
  source_scope_type: string;
  source_scope_id: string | null;
  source_scope_name: string | null;
  priority: number;
}

export interface EffectivePolicyResponse {
  repeater_id: string;
  node_name: string;
  policies: EffectivePolicyItemResponse[];
}

export interface AlertPolicyEvaluationRequest {
  repeater_id?: string;
}

export interface AlertPolicyEvaluationResponse {
  evaluated_repeaters: number;
  alerts_activated: number;
  alerts_resolved: number;
}

export interface AlertActionProviderCapabilityResponse {
  provider_type: string;
  display_name: string;
  supports_send: boolean;
  supports_templated_payload: boolean;
}

export interface AlertActionIntegrationCreateRequest {
  name: string;
  provider_type: string;
  description?: string;
  enabled?: boolean;
  settings?: Record<string, unknown>;
  secrets?: Record<string, unknown>;
}

export interface AlertActionIntegrationUpdateRequest {
  name?: string;
  description?: string | null;
  enabled?: boolean;
  settings?: Record<string, unknown>;
  secrets?: Record<string, unknown>;
}

export interface AlertActionIntegrationResponse {
  id: string;
  name: string;
  provider_type: string;
  description: string | null;
  enabled: boolean;
  settings: Record<string, unknown>;
  has_secrets: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertActionTemplateCreateRequest {
  name: string;
  provider_type?: string | null;
  description?: string;
  title_template?: string | null;
  body_template?: string | null;
  payload_template?: Record<string, unknown> | null;
  default_event_types?: string[];
  enabled?: boolean;
}

export interface AlertActionTemplateUpdateRequest {
  name?: string;
  provider_type?: string | null;
  description?: string | null;
  title_template?: string | null;
  body_template?: string | null;
  payload_template?: Record<string, unknown> | null;
  default_event_types?: string[];
  enabled?: boolean;
}

export interface AlertActionTemplateResponse {
  id: string;
  name: string;
  provider_type: string | null;
  description: string | null;
  title_template: string | null;
  body_template: string | null;
  payload_template: Record<string, unknown> | null;
  default_event_types: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertPolicyActionBindingCreateRequest {
  policy_template_id: string;
  integration_id: string;
  action_template_id: string;
  event_types?: string[];
  min_severity?: string | null;
  enabled?: boolean;
  sort_order?: number;
  cooldown_seconds?: number;
}

export interface AlertPolicyActionBindingUpdateRequest {
  event_types?: string[];
  min_severity?: string | null;
  enabled?: boolean;
  sort_order?: number;
  cooldown_seconds?: number;
}

export interface AlertPolicyActionBindingResponse {
  id: string;
  policy_template_id: string;
  integration_id: string;
  action_template_id: string;
  event_types: string[];
  min_severity: string | null;
  enabled: boolean;
  sort_order: number;
  cooldown_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface AlertActionTemplatePreviewRequest {
  action_template_id?: string;
  title_template?: string | null;
  body_template?: string | null;
  payload_template?: Record<string, unknown> | null;
  event_type?: string;
  alert_id?: string;
  repeater_id?: string;
  sample_context?: Record<string, unknown>;
}

export interface AlertActionTemplatePreviewResponse {
  event_type: string;
  title: string | null;
  body: string | null;
  payload: Record<string, unknown>;
  context: Record<string, unknown>;
}

export interface AlertActionIntegrationTestRequest {
  event_type?: string;
  payload?: Record<string, unknown>;
  rendered_payload?: Record<string, unknown> | null;
}

export interface AlertActionIntegrationTestResponse {
  status: string;
  status_code: number | null;
  provider_message_id: string | null;
  response_body: string | null;
  error: string | null;
}

export interface AlertActionDeliveryResponse {
  id: string;
  alert_id: string;
  integration_id: string | null;
  integration_name: string | null;
  action_template_id: string | null;
  action_template_name: string | null;
  binding_id: string | null;
  provider_type: string | null;
  channel: string;
  event_type: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  sent_at: string | null;
  last_error: string | null;
  response_status_code: number | null;
  provider_message_id: string | null;
  payload: Record<string, unknown>;
  rendered_payload: Record<string, unknown> | null;
  created_at: string;
}

export interface AlertActionDeliverySummaryResponse {
  total: number;
  queued: number;
  sent: number;
  failed: number;
  by_provider_type: Record<string, number>;
}

export interface ManagedMqttSettingsResponse {
  mqtt_enabled: boolean;
  mqtt_broker_host: string;
  mqtt_broker_port: number;
  mqtt_base_topic: string;
  mqtt_tls_enabled: boolean;
  source: string;
  updated_at: string | null;
}

export interface ManagedMqttSettingsUpdateRequest {
  mqtt_enabled: boolean;
  mqtt_broker_host: string;
  mqtt_broker_port: number;
  mqtt_base_topic: string;
  mqtt_tls_enabled: boolean;
  queue_to_repeaters?: boolean;
  reason?: string;
}

export interface ManagedMqttSettingsUpdateResponse {
  settings: ManagedMqttSettingsResponse;
  queued_commands: number;
}

export interface ConfigSnapshotEncryptionSettingsResponse {
  configured: boolean;
  source: string;
  key_ids: string[];
  updated_at: string | null;
}

export interface ConfigSnapshotEncryptionSettingsUpdateRequest {
  encryption_keys: string;
  reason?: string;
}

export interface ConfigSnapshotEncryptionKeyGenerateRequest {
  key_id?: string;
  replace_existing?: boolean;
  reason?: string;
}

export interface ConfigSnapshotEncryptionKeyGenerateResponse {
  settings: ConfigSnapshotEncryptionSettingsResponse;
  generated_entry: string;
}
