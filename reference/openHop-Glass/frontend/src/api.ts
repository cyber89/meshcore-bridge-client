import type {
  AlertActionDeliveryResponse,
  AlertActionDeliverySummaryResponse,
  AlertActionIntegrationCreateRequest,
  AlertActionIntegrationResponse,
  AlertActionIntegrationTestRequest,
  AlertActionIntegrationTestResponse,
  AlertActionIntegrationUpdateRequest,
  AlertActionProviderCapabilityResponse,
  AlertActionTemplatePreviewRequest,
  AlertActionTemplatePreviewResponse,
  AlertActionTemplateCreateRequest,
  AlertActionTemplateResponse,
  AlertActionTemplateUpdateRequest,
  AlertPolicyActionBindingCreateRequest,
  AlertPolicyActionBindingResponse,
  AlertPolicyActionBindingUpdateRequest,
  AlertPolicyAssignmentCreateRequest,
  AlertPolicyAssignmentResponse,
  AlertPolicyAssignmentUpdateRequest,
  AlertPolicyEvaluationRequest,
  AlertPolicyEvaluationResponse,
  AlertPolicyTemplateCreateRequest,
  AlertPolicyTemplateResponse,
  AlertPolicyTemplateUpdateRequest,
  AlertDetailResponse,
  AlertLifecycleRequest,
  AlertResponse,
  AlertSummaryResponse,
  AdoptionActionRequest,
  AdoptionActionResponse,
  AuditRecordResponse,
  BootstrapAdminRequest,
  BootstrapStatusResponse,
  CommandQueueItemResponse,
  ConfigSnapshotEncryptionKeyGenerateRequest,
  ConfigSnapshotEncryptionKeyGenerateResponse,
  ConfigSnapshotEncryptionSettingsResponse,
  ConfigSnapshotEncryptionSettingsUpdateRequest,
  ConfigSnapshotDetailResponse,
  ConfigSnapshotExportQueuedResponse,
  ConfigSnapshotExportRequest,
  ConfigSnapshotResponse,
  DeleteStaleRepeatersResponse,
  LoginResponse,
  QueueCommandResponse,
  QueueCommandRequest,
  RepeaterCreateRequest,
  RepeaterDetailResponse,
  RepeaterResponse,
  RepeaterUpdateRequest,
  ManagedMqttSettingsResponse,
  ManagedMqttSettingsUpdateRequest,
  ManagedMqttSettingsUpdateResponse,
  NeighborObservationListResponse,
  NodeDetailResponse,
  NodeTimeseriesResponse,
  TopologyPacketQualityResponse,
  TopologyPacketStructureResponse,
  PacketRecordResponse,
  PacketSummaryResponse,
  TopologyEdgeListResponse,
  TopologySummaryResponse,
  EffectivePolicyResponse,
  NodeGroupCreateRequest,
  NodeGroupDetailResponse,
  NodeGroupMemberAddRequest,
  NodeGroupResponse,
  NodeGroupUpdateRequest,
  TransportKeyCreateRequest,
  TransportKeyGroupCreateRequest,
  TransportKeyGroupResponse,
  TransportKeyGroupUpdateRequest,
  TransportKeyResponse,
  TransportKeySyncTriggerResponse,
  TransportKeyTreeResponse,
  TransportKeyUpdateRequest,
  UserCreateRequest,
  UserInfoResponse,
  UserManagementResponse,
  UserUpdateRequest,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

const envBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
const API_BASE_URL = envBase ? envBase.replace(/\/$/, "") : "";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string | null;
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers();
  const hasBody = options.body !== undefined;

  if (hasBody) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: hasBody ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;

  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const message =
      (typeof payload === "object" && payload && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : null) ??
      (typeof payload === "string" && payload.trim().length > 0
        ? payload
        : `Request failed with status ${response.status}`);

    throw new ApiError(response.status, message, payload);
  }

  return payload as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL || "(same-origin)";
}

export function getBootstrapStatus(): Promise<BootstrapStatusResponse> {
  return request<BootstrapStatusResponse>("/api/bootstrap/status");
}

export function createBootstrapAdmin(payload: BootstrapAdminRequest): Promise<void> {
  return request<void>("/api/bootstrap/admin", {
    method: "POST",
    body: payload,
  });
}

export function getManagedMqttSettings(token: string): Promise<ManagedMqttSettingsResponse> {
  return request<ManagedMqttSettingsResponse>("/api/system-settings/mqtt-managed", { token });
}

export function updateManagedMqttSettings(
  token: string,
  payload: ManagedMqttSettingsUpdateRequest,
): Promise<ManagedMqttSettingsUpdateResponse> {
  return request<ManagedMqttSettingsUpdateResponse>("/api/system-settings/mqtt-managed", {
    method: "PUT",
    token,
    body: payload,
  });
}

export function getConfigSnapshotEncryptionSettings(
  token: string,
): Promise<ConfigSnapshotEncryptionSettingsResponse> {
  return request<ConfigSnapshotEncryptionSettingsResponse>(
    "/api/system-settings/config-snapshot-encryption",
    { token },
  );
}

export function getTopologySummary(
  token: string,
  options?: { hours?: number; stale_after_hours?: number },
): Promise<TopologySummaryResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 168));
  params.set("stale_after_hours", String(options?.stale_after_hours ?? 6));
  return request<TopologySummaryResponse>(`/api/insights/topology/summary?${params.toString()}`, {
    token,
  });
}

export function listTopologyEdges(
  token: string,
  options?: {
    hours?: number;
    limit?: number;
    offset?: number;
    observer_node_name?: string;
    contact_type?: string;
    route_type?: number;
    zero_hop?: boolean;
    search?: string;
  },
): Promise<TopologyEdgeListResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 168));
  params.set("limit", String(options?.limit ?? 500));
  params.set("offset", String(options?.offset ?? 0));
  if (options?.observer_node_name) {
    params.set("observer_node_name", options.observer_node_name);
  }
  if (options?.contact_type) {
    params.set("contact_type", options.contact_type);
  }
  if (typeof options?.route_type === "number") {
    params.set("route_type", String(options.route_type));
  }
  if (typeof options?.zero_hop === "boolean") {
    params.set("zero_hop", String(options.zero_hop));
  }
  if (options?.search) {
    params.set("search", options.search);
  }
  return request<TopologyEdgeListResponse>(`/api/insights/topology/edges?${params.toString()}`, {
    token,
  });
}

export function getInsightNodeTimeseries(
  token: string,
  pubkey: string,
  options?: { hours?: number; bucket_hours?: number },
): Promise<NodeTimeseriesResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 168));
  params.set("bucket_hours", String(options?.bucket_hours ?? 6));
  return request<NodeTimeseriesResponse>(
    `/api/insights/nodes/${encodeURIComponent(pubkey)}/timeseries?${params.toString()}`,
    { token },
  );
}

export function getTopologyPacketQuality(
  token: string,
  options?: {
    hours?: number;
    bucket_minutes?: number;
    limit?: number;
    observer_node_name?: string;
  },
): Promise<TopologyPacketQualityResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 24));
  params.set("bucket_minutes", String(options?.bucket_minutes ?? 60));
  params.set("limit", String(options?.limit ?? 5000));
  if (options?.observer_node_name) {
    params.set("observer_node_name", options.observer_node_name);
  }
  return request<TopologyPacketQualityResponse>(
    `/api/insights/topology/packet-quality?${params.toString()}`,
    { token },
  );
}

export function getTopologyPacketStructure(
  token: string,
  options?: {
    hours?: number;
    limit?: number;
    top_subpaths?: number;
    top_nodes?: number;
    top_edges?: number;
  },
): Promise<TopologyPacketStructureResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 24));
  params.set("limit", String(options?.limit ?? 3000));
  params.set("top_subpaths", String(options?.top_subpaths ?? 20));
  params.set("top_nodes", String(options?.top_nodes ?? 120));
  params.set("top_edges", String(options?.top_edges ?? 120));
  return request<TopologyPacketStructureResponse>(
    `/api/insights/topology/packet-structure?${params.toString()}`,
    { token },
  );
}

export function updateConfigSnapshotEncryptionSettings(
  token: string,
  payload: ConfigSnapshotEncryptionSettingsUpdateRequest,
): Promise<ConfigSnapshotEncryptionSettingsResponse> {
  return request<ConfigSnapshotEncryptionSettingsResponse>(
    "/api/system-settings/config-snapshot-encryption",
    {
      method: "PUT",
      token,
      body: payload,
    },
  );
}

export function generateConfigSnapshotEncryptionKey(
  token: string,
  payload: ConfigSnapshotEncryptionKeyGenerateRequest,
): Promise<ConfigSnapshotEncryptionKeyGenerateResponse> {
  return request<ConfigSnapshotEncryptionKeyGenerateResponse>(
    "/api/system-settings/config-snapshot-encryption/generate",
    {
      method: "POST",
      token,
      body: payload,
    },
  );
}

export function getTelemetryStreamUrl(token: string): string {
  const encodedToken = encodeURIComponent(token);
  return `${API_BASE_URL}/api/telemetry/stream?token=${encodedToken}`;
}

export function getTopologyInsightsStreamUrl(token: string): string {
  const encodedToken = encodeURIComponent(token);
  return `${API_BASE_URL}/api/insights/topology/stream?token=${encodedToken}`;
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function getCurrentUser(token: string): Promise<UserInfoResponse> {
  return request<UserInfoResponse>("/api/auth/me", { token });
}

export function logout(token: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/api/auth/logout", {
    method: "POST",
    token,
  });
}

export function listRepeaters(token: string): Promise<RepeaterResponse[]> {
  return request<RepeaterResponse[]>("/api/repeaters", { token });
}

export function createRepeater(
  token: string,
  payload: RepeaterCreateRequest,
): Promise<RepeaterResponse> {
  return request<RepeaterResponse>("/api/repeaters", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateRepeater(
  token: string,
  repeaterId: string,
  payload: RepeaterUpdateRequest,
): Promise<RepeaterResponse> {
  return request<RepeaterResponse>(`/api/repeaters/${repeaterId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function getRepeaterDetail(
  token: string,
  repeaterId: string,
  options?: { snapshot_limit?: number; cert_log_limit?: number },
): Promise<RepeaterDetailResponse> {
  const params = new URLSearchParams();
  if (options?.snapshot_limit) {
    params.set("snapshot_limit", String(options.snapshot_limit));
  }
  if (options?.cert_log_limit) {
    params.set("cert_log_limit", String(options.cert_log_limit));
  }
  const suffix = params.toString();
  const path = suffix
    ? `/api/repeaters/${repeaterId}/detail?${suffix}`
    : `/api/repeaters/${repeaterId}/detail`;
  return request<RepeaterDetailResponse>(path, { token });
}

export function deleteRepeater(token: string, repeaterId: string): Promise<void> {
  return request<void>(`/api/repeaters/${repeaterId}`, {
    method: "DELETE",
    token,
  });
}

export function deleteStaleRepeaters(
  token: string,
  inactiveHours = 168,
): Promise<DeleteStaleRepeatersResponse> {
  return request<DeleteStaleRepeatersResponse>(
    `/api/repeaters/stale?inactive_hours=${inactiveHours}`,
    {
      method: "DELETE",
      token,
    },
  );
}

export function listPendingAdoptions(token: string): Promise<RepeaterResponse[]> {
  return request<RepeaterResponse[]>("/api/adoption/pending", { token });
}

export function adoptRepeater(
  token: string,
  repeaterId: string,
  payload: AdoptionActionRequest,
): Promise<AdoptionActionResponse> {
  return request<AdoptionActionResponse>(`/api/adoption/${repeaterId}/adopt`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function getCommand(token: string, commandId: string): Promise<CommandQueueItemResponse> {
  return request<CommandQueueItemResponse>(`/api/commands/${commandId}`, { token });
}

export function rejectRepeater(
  token: string,
  repeaterId: string,
  payload: AdoptionActionRequest,
): Promise<AdoptionActionResponse> {
  return request<AdoptionActionResponse>(`/api/adoption/${repeaterId}/reject`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function listCommands(
  token: string,
  options?: { status?: string; node_name?: string; limit?: number },
): Promise<CommandQueueItemResponse[]> {
  const params = new URLSearchParams();
  if (options?.status) {
    params.set("status", options.status);
  }
  if (options?.node_name) {
    params.set("node_name", options.node_name);
  }
  params.set("limit", String(options?.limit ?? 100));

  const suffix = params.toString();
  return request<CommandQueueItemResponse[]>(`/api/commands?${suffix}`, { token });
}

export function queueConfigSnapshotExport(
  token: string,
  payload: ConfigSnapshotExportRequest,
): Promise<ConfigSnapshotExportQueuedResponse> {
  return request<ConfigSnapshotExportQueuedResponse>("/api/config-snapshots/export", {
    method: "POST",
    token,
    body: payload,
  });
}

export function listConfigSnapshots(
  token: string,
  options?: { repeater_id?: string; node_name?: string; limit?: number },
): Promise<ConfigSnapshotResponse[]> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 100));
  if (options?.repeater_id) {
    params.set("repeater_id", options.repeater_id);
  }
  if (options?.node_name) {
    params.set("node_name", options.node_name);
  }
  return request<ConfigSnapshotResponse[]>(`/api/config-snapshots?${params.toString()}`, { token });
}

export function getConfigSnapshot(
  token: string,
  snapshotId: string,
): Promise<ConfigSnapshotDetailResponse> {
  return request<ConfigSnapshotDetailResponse>(`/api/config-snapshots/${snapshotId}`, { token });
}

export function listPackets(
  token: string,
  options?: {
    limit?: number;
    node_name?: string;
    packet_type?: string;
    route?: string;
    hours?: number;
  },
): Promise<PacketRecordResponse[]> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 200));
  if (options?.node_name) {
    params.set("node_name", options.node_name);
  }
  if (options?.packet_type) {
    params.set("packet_type", options.packet_type);
  }
  if (options?.route) {
    params.set("route", options.route);
  }
  if (typeof options?.hours === "number") {
    params.set("hours", String(options.hours));
  }
  return request<PacketRecordResponse[]>(`/api/packets?${params.toString()}`, { token });
}

export function getPacketSummary(
  token: string,
  options?: { hours?: number; node_name?: string },
): Promise<PacketSummaryResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 24));
  if (options?.node_name) {
    params.set("node_name", options.node_name);
  }
  return request<PacketSummaryResponse>(`/api/packets/summary?${params.toString()}`, { token });
}

export function listNeighborObservations(
  token: string,
  options?: {
    hours?: number;
    limit?: number;
    offset?: number;
    observer_node_name?: string;
    contact_type?: string;
    route_type?: number;
    zero_hop?: boolean;
    search?: string;
  },
): Promise<NeighborObservationListResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 168));
  params.set("limit", String(options?.limit ?? 300));
  params.set("offset", String(options?.offset ?? 0));
  if (options?.observer_node_name) {
    params.set("observer_node_name", options.observer_node_name);
  }
  if (options?.contact_type) {
    params.set("contact_type", options.contact_type);
  }
  if (typeof options?.route_type === "number") {
    params.set("route_type", String(options.route_type));
  }
  if (typeof options?.zero_hop === "boolean") {
    params.set("zero_hop", String(options.zero_hop));
  }
  if (options?.search) {
    params.set("search", options.search);
  }
  return request<NeighborObservationListResponse>(
    `/api/insights/neighbors/latest?${params.toString()}`,
    { token },
  );
}

export function getInsightNodeDetail(
  token: string,
  pubkey: string,
  options?: { hours?: number },
): Promise<NodeDetailResponse> {
  const params = new URLSearchParams();
  params.set("hours", String(options?.hours ?? 168));
  return request<NodeDetailResponse>(
    `/api/insights/nodes/${encodeURIComponent(pubkey)}?${params.toString()}`,
    { token },
  );
}

export function listAlerts(
  token: string,
  options?: {
    state?: string;
    severity?: string;
    alert_type?: string;
    repeater_id?: string;
    node_name?: string;
    limit?: number;
    offset?: number;
  },
): Promise<AlertResponse[]> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 100));
  params.set("offset", String(options?.offset ?? 0));
  if (options?.state) {
    params.set("state", options.state);
  }
  if (options?.severity) {
    params.set("severity", options.severity);
  }
  if (options?.alert_type) {
    params.set("alert_type", options.alert_type);
  }
  if (options?.repeater_id) {
    params.set("repeater_id", options.repeater_id);
  }
  if (options?.node_name) {
    params.set("node_name", options.node_name);
  }
  return request<AlertResponse[]>(`/api/alerts?${params.toString()}`, { token });
}

export function getAlertSummary(token: string): Promise<AlertSummaryResponse> {
  return request<AlertSummaryResponse>("/api/alerts/summary", { token });
}

export function getAlertDetail(token: string, alertId: string): Promise<AlertDetailResponse> {
  return request<AlertDetailResponse>(`/api/alerts/${alertId}`, { token });
}

export function acknowledgeAlert(
  token: string,
  alertId: string,
  payload: AlertLifecycleRequest,
): Promise<AlertResponse> {
  return request<AlertResponse>(`/api/alerts/${alertId}/ack`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function resolveAlert(
  token: string,
  alertId: string,
  payload: AlertLifecycleRequest,
): Promise<AlertResponse> {
  return request<AlertResponse>(`/api/alerts/${alertId}/resolve`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function suppressAlert(
  token: string,
  alertId: string,
  payload: AlertLifecycleRequest,
): Promise<AlertResponse> {
  return request<AlertResponse>(`/api/alerts/${alertId}/suppress`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function listNodeGroups(token: string): Promise<NodeGroupResponse[]> {
  return request<NodeGroupResponse[]>("/api/node-groups", { token });
}

export function createNodeGroup(
  token: string,
  payload: NodeGroupCreateRequest,
): Promise<NodeGroupResponse> {
  return request<NodeGroupResponse>("/api/node-groups", {
    method: "POST",
    token,
    body: payload,
  });
}

export function getNodeGroup(token: string, groupId: string): Promise<NodeGroupDetailResponse> {
  return request<NodeGroupDetailResponse>(`/api/node-groups/${groupId}`, { token });
}

export function updateNodeGroup(
  token: string,
  groupId: string,
  payload: NodeGroupUpdateRequest,
): Promise<NodeGroupResponse> {
  return request<NodeGroupResponse>(`/api/node-groups/${groupId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteNodeGroup(token: string, groupId: string): Promise<void> {
  return request<void>(`/api/node-groups/${groupId}`, { method: "DELETE", token });
}

export function addNodeGroupMember(
  token: string,
  groupId: string,
  payload: NodeGroupMemberAddRequest,
): Promise<NodeGroupDetailResponse> {
  return request<NodeGroupDetailResponse>(`/api/node-groups/${groupId}/members`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function removeNodeGroupMember(
  token: string,
  groupId: string,
  repeaterId: string,
): Promise<NodeGroupDetailResponse> {
  return request<NodeGroupDetailResponse>(`/api/node-groups/${groupId}/members/${repeaterId}`, {
    method: "DELETE",
    token,
  });
}

export function getTransportKeyTree(token: string): Promise<TransportKeyTreeResponse> {
  return request<TransportKeyTreeResponse>("/api/transport-keys/tree", { token });
}

export function createTransportKeyGroup(
  token: string,
  payload: TransportKeyGroupCreateRequest,
): Promise<TransportKeyGroupResponse> {
  return request<TransportKeyGroupResponse>("/api/transport-keys/groups", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateTransportKeyGroup(
  token: string,
  groupId: string,
  payload: TransportKeyGroupUpdateRequest,
): Promise<TransportKeyGroupResponse> {
  return request<TransportKeyGroupResponse>(`/api/transport-keys/groups/${groupId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function moveTransportKeyGroup(
  token: string,
  groupId: string,
  payload: { parent_group_id?: string | null; sort_order?: number },
): Promise<TransportKeyGroupResponse> {
  return request<TransportKeyGroupResponse>(`/api/transport-keys/groups/${groupId}/move`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function deleteTransportKeyGroup(
  token: string,
  groupId: string,
  reassignToGroupId?: string | null,
): Promise<void> {
  const params = new URLSearchParams();
  if (reassignToGroupId) {
    params.set("reassign_to_group_id", reassignToGroupId);
  }
  const suffix = params.toString();
  const path = suffix
    ? `/api/transport-keys/groups/${groupId}?${suffix}`
    : `/api/transport-keys/groups/${groupId}`;
  return request<void>(path, {
    method: "DELETE",
    token,
  });
}

export function createTransportKey(
  token: string,
  payload: TransportKeyCreateRequest,
): Promise<TransportKeyResponse> {
  return request<TransportKeyResponse>("/api/transport-keys/keys", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateTransportKey(
  token: string,
  keyId: string,
  payload: TransportKeyUpdateRequest,
): Promise<TransportKeyResponse> {
  return request<TransportKeyResponse>(`/api/transport-keys/keys/${keyId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteTransportKey(token: string, keyId: string): Promise<void> {
  return request<void>(`/api/transport-keys/keys/${keyId}`, {
    method: "DELETE",
    token,
  });
}

export function triggerTransportKeySync(token: string): Promise<TransportKeySyncTriggerResponse> {
  return request<TransportKeySyncTriggerResponse>("/api/transport-keys/sync", {
    method: "POST",
    token,
  });
}

export function listAlertPolicyTemplates(token: string): Promise<AlertPolicyTemplateResponse[]> {
  return request<AlertPolicyTemplateResponse[]>("/api/alert-policies/templates", { token });
}

export function createAlertPolicyTemplate(
  token: string,
  payload: AlertPolicyTemplateCreateRequest,
): Promise<AlertPolicyTemplateResponse> {
  return request<AlertPolicyTemplateResponse>("/api/alert-policies/templates", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateAlertPolicyTemplate(
  token: string,
  templateId: string,
  payload: AlertPolicyTemplateUpdateRequest,
): Promise<AlertPolicyTemplateResponse> {
  return request<AlertPolicyTemplateResponse>(`/api/alert-policies/templates/${templateId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteAlertPolicyTemplate(token: string, templateId: string): Promise<void> {
  return request<void>(`/api/alert-policies/templates/${templateId}`, {
    method: "DELETE",
    token,
  });
}

export function listAlertPolicyAssignments(token: string): Promise<AlertPolicyAssignmentResponse[]> {
  return request<AlertPolicyAssignmentResponse[]>("/api/alert-policies/assignments", { token });
}

export function createAlertPolicyAssignment(
  token: string,
  payload: AlertPolicyAssignmentCreateRequest,
): Promise<AlertPolicyAssignmentResponse> {
  return request<AlertPolicyAssignmentResponse>("/api/alert-policies/assignments", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateAlertPolicyAssignment(
  token: string,
  assignmentId: string,
  payload: AlertPolicyAssignmentUpdateRequest,
): Promise<AlertPolicyAssignmentResponse> {
  return request<AlertPolicyAssignmentResponse>(`/api/alert-policies/assignments/${assignmentId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteAlertPolicyAssignment(token: string, assignmentId: string): Promise<void> {
  return request<void>(`/api/alert-policies/assignments/${assignmentId}`, {
    method: "DELETE",
    token,
  });
}

export function getEffectiveAlertPolicies(
  token: string,
  repeaterId: string,
): Promise<EffectivePolicyResponse> {
  return request<EffectivePolicyResponse>(`/api/alert-policies/effective/${repeaterId}`, { token });
}

export function evaluateAlertPolicies(
  token: string,
  payload: AlertPolicyEvaluationRequest,
): Promise<AlertPolicyEvaluationResponse> {
  return request<AlertPolicyEvaluationResponse>("/api/alert-policies/evaluate", {
    method: "POST",
    token,
    body: payload,
  });
}

export function bootstrapDefaultAlertPolicies(token: string): Promise<AlertPolicyTemplateResponse[]> {
  return request<AlertPolicyTemplateResponse[]>("/api/alert-policies/bootstrap-defaults", {
    method: "POST",
    token,
  });
}

export function listAlertActionProviders(
  token: string,
): Promise<AlertActionProviderCapabilityResponse[]> {
  return request<AlertActionProviderCapabilityResponse[]>("/api/alert-actions/providers", { token });
}

export function listAlertActionIntegrations(
  token: string,
): Promise<AlertActionIntegrationResponse[]> {
  return request<AlertActionIntegrationResponse[]>("/api/alert-actions/integrations", { token });
}

export function createAlertActionIntegration(
  token: string,
  payload: AlertActionIntegrationCreateRequest,
): Promise<AlertActionIntegrationResponse> {
  return request<AlertActionIntegrationResponse>("/api/alert-actions/integrations", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateAlertActionIntegration(
  token: string,
  integrationId: string,
  payload: AlertActionIntegrationUpdateRequest,
): Promise<AlertActionIntegrationResponse> {
  return request<AlertActionIntegrationResponse>(`/api/alert-actions/integrations/${integrationId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteAlertActionIntegration(token: string, integrationId: string): Promise<void> {
  return request<void>(`/api/alert-actions/integrations/${integrationId}`, {
    method: "DELETE",
    token,
  });
}

export function listAlertActionTemplates(token: string): Promise<AlertActionTemplateResponse[]> {
  return request<AlertActionTemplateResponse[]>("/api/alert-actions/templates", { token });
}

export function createAlertActionTemplate(
  token: string,
  payload: AlertActionTemplateCreateRequest,
): Promise<AlertActionTemplateResponse> {
  return request<AlertActionTemplateResponse>("/api/alert-actions/templates", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateAlertActionTemplate(
  token: string,
  templateId: string,
  payload: AlertActionTemplateUpdateRequest,
): Promise<AlertActionTemplateResponse> {
  return request<AlertActionTemplateResponse>(`/api/alert-actions/templates/${templateId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteAlertActionTemplate(token: string, templateId: string): Promise<void> {
  return request<void>(`/api/alert-actions/templates/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
    token,
  });
}

export function listAlertPolicyActionBindings(token: string): Promise<AlertPolicyActionBindingResponse[]> {
  return request<AlertPolicyActionBindingResponse[]>("/api/alert-actions/bindings", { token });
}

export function createAlertPolicyActionBinding(
  token: string,
  payload: AlertPolicyActionBindingCreateRequest,
): Promise<AlertPolicyActionBindingResponse> {
  return request<AlertPolicyActionBindingResponse>("/api/alert-actions/bindings", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateAlertPolicyActionBinding(
  token: string,
  bindingId: string,
  payload: AlertPolicyActionBindingUpdateRequest,
): Promise<AlertPolicyActionBindingResponse> {
  return request<AlertPolicyActionBindingResponse>(`/api/alert-actions/bindings/${bindingId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function deleteAlertPolicyActionBinding(token: string, bindingId: string): Promise<void> {
  return request<void>(`/api/alert-actions/bindings/${encodeURIComponent(bindingId)}`, {
    method: "DELETE",
    token,
  });
}

export function previewAlertActionTemplate(
  token: string,
  payload: AlertActionTemplatePreviewRequest,
): Promise<AlertActionTemplatePreviewResponse> {
  return request<AlertActionTemplatePreviewResponse>("/api/alert-actions/templates/preview", {
    method: "POST",
    token,
    body: payload,
  });
}

export function testAlertActionIntegration(
  token: string,
  integrationId: string,
  payload: AlertActionIntegrationTestRequest,
): Promise<AlertActionIntegrationTestResponse> {
  return request<AlertActionIntegrationTestResponse>(`/api/alert-actions/integrations/${integrationId}/test`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function listAlertActionDeliveries(
  token: string,
  options?: {
    status?: string;
    provider_type?: string;
    alert_id?: string;
    integration_id?: string;
    limit?: number;
    offset?: number;
  },
): Promise<AlertActionDeliveryResponse[]> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 100));
  params.set("offset", String(options?.offset ?? 0));
  if (options?.status) {
    params.set("status", options.status);
  }
  if (options?.provider_type) {
    params.set("provider_type", options.provider_type);
  }
  if (options?.alert_id) {
    params.set("alert_id", options.alert_id);
  }
  if (options?.integration_id) {
    params.set("integration_id", options.integration_id);
  }
  return request<AlertActionDeliveryResponse[]>(`/api/alert-actions/deliveries?${params.toString()}`, {
    token,
  });
}

export function getAlertActionDeliverySummary(
  token: string,
): Promise<AlertActionDeliverySummaryResponse> {
  return request<AlertActionDeliverySummaryResponse>("/api/alert-actions/deliveries/summary", {
    token,
  });
}

export function queueCommand(
  token: string,
  payload: QueueCommandRequest,
): Promise<QueueCommandResponse> {
  return request<QueueCommandResponse>("/api/commands", {
    method: "POST",
    token,
    body: payload,
  });
}

export function listAudit(token: string, limit = 100): Promise<AuditRecordResponse[]> {
  return request<AuditRecordResponse[]>(`/api/audit?limit=${limit}`, { token });
}

export function listUsers(token: string): Promise<UserManagementResponse[]> {
  return request<UserManagementResponse[]>("/api/users", { token });
}

export function createUser(
  token: string,
  payload: UserCreateRequest,
): Promise<UserManagementResponse> {
  return request<UserManagementResponse>("/api/users", {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateUser(
  token: string,
  userId: string,
  payload: UserUpdateRequest,
): Promise<UserManagementResponse> {
  return request<UserManagementResponse>(`/api/users/${userId}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}
