<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Dashboard</h1>
        <p class="section-subtitle">
          Live snapshot of fleet posture, command reliability, and operator activity.
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="isRefreshing" @click="refreshDashboard()">
        {{ isRefreshing ? "Refreshing..." : "Refresh data" }}
      </button>
    </header>

    <section class="grid-3">
      <UiStatCard title="Total Repeaters" :value="appState.repeaters.length" />
      <UiStatCard title="Pending Adoption" :value="appState.pendingRepeaters.length" />
      <UiStatCard title="No Inform >10m" :value="staleInformRepeaters.length" />
    </section>
    <section class="grid-1">
      <article class="glass-card panel">
        <h2>Connectivity Warnings</h2>
        <p class="section-subtitle">
          Connected repeaters with no inform in the last 10 minutes are flagged as possible cert/TLS issues.
        </p>
        <UiDataTable>
          <thead>
            <tr>
              <th>Node</th>
              <th>Status</th>
              <th>Last inform</th>
              <th>Age</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in connectedSilentRepeaters.slice(0, 8)" :key="row.id">
              <td>
                <router-link :to="`/repeaters/${row.id}`">{{ row.node_name }}</router-link>
              </td>
              <td><StatusPill :status="row.status" /></td>
              <td>{{ formatTimestamp(row.last_inform_at) }}</td>
              <td>{{ formatAgeMinutes(row.last_inform_at) }}</td>
              <td><span class="pill pill-yellow">possible cert/tls issue</span></td>
            </tr>
            <tr v-if="connectedSilentRepeaters.length === 0">
              <td colspan="5" class="section-subtitle">No connected-silent repeaters detected.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
    </section>

    <section class="grid-2">
      <UiPanelCard title="Global Packet Snapshot" subtitle="24h packet activity across all repeaters.">
        <div class="mini-grid">
          <div>
            <p class="section-subtitle">Unique repeaters</p>
            <strong>{{ packetSummary?.unique_repeaters ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Unique sources</p>
            <strong>{{ packetSummary?.unique_sources ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Average RSSI</p>
            <strong>{{ formatSignal(packetSummary?.avg_rssi, "dBm") }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Average SNR</p>
            <strong>{{ formatSignal(packetSummary?.avg_snr, "dB") }}</strong>
          </div>
        </div>
        <router-link class="btn btn-ghost btn-sm" to="/global-stats">
          Open full Global Stats
        </router-link>
      </UiPanelCard>

      <UiPanelCard
        title="Recent Fleet Packets"
        subtitle="Most recent packets seen across all repeaters."
      >
        <UiDataTable>
          <thead>
            <tr>
              <th>Time</th>
              <th>Node</th>
              <th>Type</th>
              <th>Route</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="packet in recentPackets" :key="packet.id">
              <td>{{ formatTimestamp(packet.timestamp) }}</td>
              <td>{{ packet.node_name }}</td>
              <td>{{ formatPacketType(packet.packet_type) }}</td>
              <td>{{ formatRoute(packet.route) }}</td>
            </tr>
            <tr v-if="!packetPreviewLoading && recentPackets.length === 0">
              <td colspan="4" class="section-subtitle">No packet records available.</td>
            </tr>
            <tr v-if="packetPreviewLoading">
              <td colspan="4" class="section-subtitle">Loading packet preview...</td>
            </tr>
          </tbody>
        </UiDataTable>
      </UiPanelCard>
    </section>

    <section class="grid-3">
      <UiPanelCard title="Topology Freshness" subtitle="Advert versus MQTT recency over the last 24h.">
        <div class="mini-grid highlight-grid">
          <div>
            <p class="section-subtitle">Advert lag</p>
            <strong>{{ formatLag(topologySummary?.topology_advert_lag_seconds) }}</strong>
          </div>
          <div>
            <p class="section-subtitle">MQTT overall lag</p>
            <strong>{{ formatLag(topologySummary?.mqtt_overall_lag_seconds) }}</strong>
          </div>
          <div>
            <p class="section-subtitle">MQTT packet lag</p>
            <strong>{{ formatLag(topologySummary?.mqtt_packet_lag_seconds) }}</strong>
          </div>
          <div>
            <p class="section-subtitle">MQTT event lag</p>
            <strong>{{ formatLag(topologySummary?.mqtt_event_lag_seconds) }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Stale nodes</p>
            <strong>{{ topologySummary?.stale_nodes ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Top observer</p>
            <strong>{{ topologySummary?.top_observer_node_name ?? "—" }}</strong>
          </div>
        </div>
        <p v-if="isTopologyAdvertStale" class="warning-text">Topology advert feed appears stale.</p>
        <router-link class="btn btn-ghost btn-sm" to="/insights/topology">
          Open Topology Insights
        </router-link>
      </UiPanelCard>

      <UiPanelCard title="Packet Transport Highlights" subtitle="Route/type leaders and signal quality from packet stream.">
        <div class="mini-grid highlight-grid">
          <div>
            <p class="section-subtitle">Packets analyzed</p>
            <strong>{{ topologyPacketQuality?.total_packets ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Avg RSSI</p>
            <strong>{{ formatSignal(topologyPacketQuality?.avg_rssi, "dBm") }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Avg SNR</p>
            <strong>{{ formatSignal(topologyPacketQuality?.avg_snr, "dB") }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Top route</p>
            <strong>{{ topRouteHighlight?.label ?? "—" }}</strong>
            <p class="section-subtitle">{{ topRouteHighlight?.count ?? 0 }} packets</p>
          </div>
          <div>
            <p class="section-subtitle">Top packet type</p>
            <strong>{{ topPacketTypeHighlight?.label ?? "—" }}</strong>
            <p class="section-subtitle">{{ topPacketTypeHighlight?.count ?? 0 }} packets</p>
          </div>
          <div>
            <p class="section-subtitle">Top repeater share</p>
            <strong>{{ topRepeaterShare ? `${topRepeaterShare.share_percent.toFixed(1)}%` : "—" }}</strong>
            <p class="section-subtitle">{{ topRepeaterShare?.repeater_node_name ?? "—" }}</p>
          </div>
        </div>
      </UiPanelCard>

      <UiPanelCard title="Packet Structure Health" subtitle="Decode coverage and graph-level packet structure signals.">
        <div class="mini-grid highlight-grid">
          <div>
            <p class="section-subtitle">Packet events scanned</p>
            <strong>{{ topologyPacketStructure?.total_packet_events ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Decoded hop coverage</p>
            <strong>{{ topologyPacketStructure ? `${topologyPacketStructure.decode_coverage_percent.toFixed(1)}%` : "—" }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Graph nodes</p>
            <strong>{{ topologyPacketStructure?.neighbor_graph_nodes.length ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Graph edges</p>
            <strong>{{ topologyPacketStructure?.neighbor_graph_edges.length ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Channel detail packets</p>
            <strong>{{ topologyPacketStructure?.packets_with_channel_details ?? 0 }}</strong>
          </div>
          <div>
            <p class="section-subtitle">Top subpath</p>
            <strong>{{ topSubpathLabel }}</strong>
          </div>
        </div>
      </UiPanelCard>
    </section>

    <section class="grid-1">
      <article class="glass-card panel">
        <div class="panel-header-inline">
          <h2>Live MQTT Telemetry</h2>
          <span class="pill" :class="appState.telemetryConnected ? 'pill-green' : 'pill-red'">
            {{ appState.telemetryConnected ? "connected" : "disconnected" }}
          </span>
        </div>
        <p class="section-subtitle">
          Streaming via SSE from backend MQTT ingest.
          Last event: {{ formatTimestamp(appState.telemetryLastEventAt) }}.
        </p>
        <UiDataTable>
          <thead>
            <tr>
              <th>Ingested</th>
              <th>Node</th>
              <th>Type</th>
              <th>Topic</th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="event in telemetryPreview" :key="event.event_id">
              <td>{{ formatTimestamp(event.ingested_at) }}</td>
              <td>{{ event.node_name }}</td>
              <td>{{ formatTelemetryType(event.event_type, event.event_name) }}</td>
              <td><code>{{ event.topic }}</code></td>
              <td><code>{{ formatTelemetryPayload(event.payload) }}</code></td>
            </tr>
            <tr v-if="telemetryPreview.length === 0">
              <td colspan="5" class="section-subtitle">
                Waiting for MQTT telemetry events.
              </td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
    </section>

    <section class="grid-2">
      <article class="glass-card panel">
        <h2>Repeater Status Chart</h2>
        <p class="section-subtitle" v-if="statusBars.length === 0">No repeater records available.</p>
        <div v-else class="bar-stack">
          <div v-for="bar in statusBars" :key="bar.status" class="bar-row">
            <div class="bar-label">
              <StatusPill :status="bar.status" />
              <span>{{ bar.count }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill status-fill" :style="{ width: `${bar.percent}%` }" />
            </div>
          </div>
        </div>
      </article>

      <article class="glass-card panel">
        <h2>Command Status Chart</h2>
        <p class="section-subtitle" v-if="commandBars.length === 0">No command activity yet.</p>
        <div v-else class="bar-stack">
          <div v-for="bar in commandBars" :key="bar.status" class="bar-row">
            <div class="bar-label">
              <StatusPill :status="bar.status" />
              <span>{{ bar.count }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill command-fill" :style="{ width: `${bar.percent}%` }" />
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="grid-3">
      <UiStatCard
        title="Adoption Rate"
        :value="`${adoptionRate}%`"
        subtitle="Adopted repeaters / total inventory."
      />
      <UiStatCard
        title="Command Success Rate"
        :value="`${commandSuccessRate}%`"
        subtitle="Successful commands / completed commands."
      />
      <UiStatCard
        title="Audit Volume (24h)"
        :value="last24hAuditCount"
        subtitle="Recent audit records in the last day."
      />
    </section>

    <section class="grid-1">

      <article class="glass-card panel">
        <h2>Top Node Activity</h2>
        <div v-if="nodeActivity.length === 0" class="section-subtitle">No command records yet.</div>
        <div v-else class="bar-stack">
          <div v-for="item in nodeActivity" :key="item.nodeName" class="bar-row">
            <div class="bar-label">
              <span class="pill pill-gray">{{ item.nodeName }}</span>
              <span>{{ item.count }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill node-fill" :style="{ width: `${item.percent}%` }" />
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="grid-2">
      <div class="panel-column">
        <article class="glass-card panel">
          <h2>Recent Repeaters</h2>
          <UiDataTable>
            <thead>
              <tr>
                <th>Node</th>
                <th>Status</th>
                <th>Firmware</th>
                <th>Last inform</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="repeater in recentRepeaters" :key="repeater.id">
                <td>
                  <strong>{{ repeater.node_name }}</strong>
                </td>
                <td><StatusPill :status="repeater.status" /></td>
                <td>{{ repeater.firmware_version || "—" }}</td>
                <td>{{ formatTimestamp(repeater.last_inform_at) }}</td>
              </tr>
              <tr v-if="recentRepeaters.length === 0">
                <td colspan="4" class="section-subtitle">No repeater records available.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </article>

        <article class="glass-card panel">
          <h2>Audit Activity Trend (7d)</h2>
          <div v-if="auditTrend.length === 0" class="section-subtitle">No audit activity available.</div>
          <div v-else class="trend-chart">
            <div v-for="point in auditTrend" :key="point.day" class="trend-bar">
              <div class="trend-fill" :style="{ height: `${point.percent}%` }" />
              <span>{{ point.value }}</span>
              <small>{{ point.day }}</small>
            </div>
          </div>
        </article>
      </div>

      <article class="glass-card panel">
        <h2>Recent Audit Events</h2>
        <UiDataTable>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Target</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in recentAudit" :key="entry.id">
              <td>{{ formatTimestamp(entry.timestamp) }}</td>
              <td>{{ entry.action }}</td>
              <td>{{ entry.target_type || "—" }} · {{ entry.target_id || "—" }}</td>
            </tr>
            <tr v-if="recentAudit.length === 0">
              <td colspan="3" class="section-subtitle">No audit entries found.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  getPacketSummary,
  getTopologyPacketQuality,
  getTopologyPacketStructure,
  getTopologySummary,
  listPackets,
} from "../api";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";

import StatusPill from "../components/ui/StatusPill.vue";
import { appState, formatTimestamp, refreshAllData } from "../state/appState";
import type {
  PacketRecordResponse,
  PacketSummaryResponse,
  TopologyPacketQualityResponse,
  TopologyPacketStructureResponse,
  TopologySummaryResponse,
} from "../types";

const packetSummary = ref<PacketSummaryResponse | null>(null);
const recentPackets = ref<PacketRecordResponse[]>([]);
const topologySummary = ref<TopologySummaryResponse | null>(null);
const topologyPacketQuality = ref<TopologyPacketQualityResponse | null>(null);
const topologyPacketStructure = ref<TopologyPacketStructureResponse | null>(null);
const packetPreviewLoading = ref(false);
const isRefreshing = computed(() => appState.dataLoading || packetPreviewLoading.value);

const PACKET_TYPE_LABELS: Record<string, string> = {
  "0": "Request",
  "1": "Response",
  "2": "Plain Text Message",
  "3": "Acknowledgment",
  "4": "Node Advertisement",
  "5": "Group Text Message",
  "6": "Group Datagram",
  "7": "Anonymous Request",
  "8": "Returned Path",
  "9": "Trace",
  "10": "Multi-part Packet",
  "11": "Control",
  "15": "Custom Packet",
};
const ROUTE_LABELS: Record<string, string> = {
  "0": "Transport Flood",
  "1": "Flood",
  "2": "Direct",
  "3": "Transport Direct",
};

const recentRepeaters = computed(() => appState.repeaters.slice(0, 8));
const recentAudit = computed(() => appState.audits.slice(0, 8));
const telemetryPreview = computed(() => appState.telemetryEvents.slice(0, 5));
const staleInformRepeaters = computed(() =>
  appState.repeaters.filter((repeater) => hasInformWarning(repeater.last_inform_at)),
);
const connectedSilentRepeaters = computed(() =>
  appState.repeaters.filter(
    (repeater) => repeater.status === "connected" && hasInformWarning(repeater.last_inform_at),
  ),
);
const isTopologyAdvertStale = computed(
  () =>
    topologySummary.value?.topology_advert_lag_seconds != null &&
    topologySummary.value.topology_advert_lag_seconds > 900,
);
const topRouteHighlight = computed(() =>
  topMixEntry(topologyPacketQuality.value?.route_mix ?? {}, formatRoute),
);
const topPacketTypeHighlight = computed(() =>
  topMixEntry(topologyPacketQuality.value?.packet_type_mix ?? {}, formatPacketType),
);
const topRepeaterShare = computed(
  () => topologyPacketQuality.value?.repeater_traffic_share[0] ?? null,
);
const topSubpathLabel = computed(() => {
  const topSubpath = topologyPacketStructure.value?.top_subpaths[0];
  if (!topSubpath || topSubpath.hops.length === 0) {
    return "—";
  }
  return topSubpath.hops.join(" → ");
});

const statusBars = computed(() => {
  const total = appState.repeaters.length || 1;
  const counts: Record<string, number> = {};
  for (const repeater of appState.repeaters) {
    counts[repeater.status] = (counts[repeater.status] ?? 0) + 1;
  }
  return Object.entries(counts)
    .map(([status, count]) => ({
      status,
      count,
      percent: Math.max(8, Math.round((count / total) * 100)),
    }))
    .sort((a, b) => b.count - a.count);
});

const commandBars = computed(() => {
  const total = appState.commands.length || 1;
  const counts: Record<string, number> = {};
  for (const command of appState.commands) {
    counts[command.status] = (counts[command.status] ?? 0) + 1;
  }
  return Object.entries(counts)
    .map(([status, count]) => ({
      status,
      count,
      percent: Math.max(8, Math.round((count / total) * 100)),
    }))
    .sort((a, b) => b.count - a.count);
});

const adoptionRate = computed(() => {
  if (appState.repeaters.length === 0) {
    return 0;
  }
  const adopted = appState.repeaters.filter((item) => item.status === "adopted").length;
  return Math.round((adopted / appState.repeaters.length) * 100);
});

const commandSuccessRate = computed(() => {
  const completed = appState.commands.filter((item) => ["success", "failed"].includes(item.status));
  if (completed.length === 0) {
    return 0;
  }
  const success = completed.filter((item) => item.status === "success").length;
  return Math.round((success / completed.length) * 100);
});

const last24hAuditCount = computed(() => {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  return appState.audits.filter((entry) => new Date(entry.timestamp).getTime() >= cutoff).length;
});

const auditTrend = computed(() => {
  const dayMs = 24 * 60 * 60 * 1000;
  const counts = new Map<string, number>();
  for (let offset = 6; offset >= 0; offset -= 1) {
    const bucket = new Date(Date.now() - offset * dayMs).toISOString().slice(5, 10);
    counts.set(bucket, 0);
  }
  for (const entry of appState.audits) {
    const bucket = new Date(entry.timestamp).toISOString().slice(5, 10);
    if (counts.has(bucket)) {
      counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
    }
  }
  const max = Math.max(1, ...Array.from(counts.values()));
  return Array.from(counts.entries()).map(([day, value]) => ({
    day,
    value,
    percent: Math.round((value / max) * 100),
  }));
});

const nodeActivity = computed(() => {
  const counts = new Map<string, number>();
  for (const command of appState.commands) {
    counts.set(command.node_name, (counts.get(command.node_name) ?? 0) + 1);
  }
  const sorted = Array.from(counts.entries())
    .map(([nodeName, count]) => ({ nodeName, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const max = Math.max(1, ...sorted.map((item) => item.count));
  return sorted.map((item) => ({
    ...item,
    percent: Math.max(10, Math.round((item.count / max) * 100)),
  }));
});

watch(
  () => appState.token,
  async (token) => {
    if (token) {
      await loadPacketPreview();
    }
  },
);

onMounted(async () => {
  await loadPacketPreview();
});

async function refreshDashboard(): Promise<void> {
  await Promise.all([refreshAllData(), loadPacketPreview()]);
}

async function loadPacketPreview(): Promise<void> {
  if (!appState.token) {
    return;
  }
  packetPreviewLoading.value = true;
  try {
    const [
      summaryResult,
      packetResult,
      topologySummaryResult,
      topologyPacketQualityResult,
      topologyPacketStructureResult,
    ] = await Promise.allSettled([
      getPacketSummary(appState.token, { hours: 24 }),
      listPackets(appState.token, { hours: 24, limit: 8 }),
      getTopologySummary(appState.token, { hours: 24, stale_after_hours: 6 }),
      getTopologyPacketQuality(appState.token, { hours: 24, bucket_minutes: 60, limit: 1500 }),
      getTopologyPacketStructure(appState.token, {
        hours: 24,
        limit: 1200,
        top_subpaths: 10,
        top_nodes: 80,
        top_edges: 80,
      }),
    ]);

    packetSummary.value = summaryResult.status === "fulfilled" ? summaryResult.value : null;
    recentPackets.value = packetResult.status === "fulfilled" ? packetResult.value : [];
    topologySummary.value =
      topologySummaryResult.status === "fulfilled" ? topologySummaryResult.value : null;
    topologyPacketQuality.value =
      topologyPacketQualityResult.status === "fulfilled" ? topologyPacketQualityResult.value : null;
    topologyPacketStructure.value =
      topologyPacketStructureResult.status === "fulfilled" ? topologyPacketStructureResult.value : null;
  } finally {
    packetPreviewLoading.value = false;
  }
}

function formatSignal(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return "—";
  }
  return `${value.toFixed(1)} ${unit}`;
}

function formatLag(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m`;
  }
  return `${(seconds / 3600).toFixed(1)}h`;
}

function topMixEntry(
  counts: Record<string, number>,
  formatter: (raw: string | null | undefined) => string,
): { label: string; count: number } | null {
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return null;
  }
  let topKey = entries[0][0];
  let topCount = entries[0][1];
  for (const [key, count] of entries.slice(1)) {
    if (count > topCount) {
      topKey = key;
      topCount = count;
    }
  }
  return {
    label: formatter(topKey),
    count: topCount,
  };
}

function formatPacketType(raw: string | null | undefined): string {
  const key = (raw || "unknown").trim();
  if (!key || key === "unknown") {
    return "Unknown";
  }
  if (PACKET_TYPE_LABELS[key]) {
    return PACKET_TYPE_LABELS[key];
  }
  return formatTokenLabel(key);
}

function formatRoute(raw: string | null | undefined): string {
  const key = (raw || "unknown").trim();
  if (!key || key === "unknown") {
    return "Unknown";
  }
  if (ROUTE_LABELS[key]) {
    return ROUTE_LABELS[key];
  }
  return formatTokenLabel(key);
}

function formatTokenLabel(raw: string): string {
  const token = raw.replace(/[_-]+/g, " ").trim();
  if (!token) {
    return "Unknown";
  }
  return token
    .split(" ")
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase())
    .join(" ");
}

function formatTelemetryType(eventType: string, eventName: string | null): string {
  if (eventType !== "event") {
    return eventType;
  }
  return eventName ? `event:${eventName}` : "event";
}

function formatTelemetryPayload(payload: Record<string, unknown>): string {
  try {
    return JSON.stringify(payload);
  } catch {
    return "{}";
  }
}

function hasInformWarning(lastInformAt: string | null): boolean {
  if (!lastInformAt) {
    return true;
  }
  const timestamp = new Date(lastInformAt).getTime();
  if (Number.isNaN(timestamp)) {
    return true;
  }
  return Date.now() - timestamp > 10 * 60 * 1000;
}

function formatAgeMinutes(lastInformAt: string | null): string {
  if (!lastInformAt) {
    return "unknown";
  }
  const timestamp = new Date(lastInformAt).getTime();
  if (Number.isNaN(timestamp)) {
    return "unknown";
  }
  const deltaMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / (60 * 1000)));
  return `${deltaMinutes}m`;
}
</script>

<style scoped>
.warning-text {
  color: #f5c159;
  font-size: 0.88rem;
}

.panel h2 {
  font-size: 1rem;
}

.panel-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.mini-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mini-grid strong {
  color: var(--color-text-primary);
  font-size: 1.05rem;
}
.highlight-grid {
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}
.panel-column {
  display: grid;
  gap: 1rem;
}


.bar-stack {
  display: grid;
  gap: 0.56rem;
}

.bar-row {
  display: grid;
  gap: 0.35rem;
}

.bar-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.bar-track {
  height: 9px;
  border-radius: 999px;
  overflow: hidden;
  background: #1f2b3e;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
}

.status-fill {
  background: linear-gradient(90deg, #1d9a93, #60d8cb);
}

.command-fill {
  background: linear-gradient(90deg, #625ee4, #8679f7);
}

.node-fill {
  background: linear-gradient(90deg, #3880cf, #7bb1f0);
}

.trend-chart {
  display: flex;
  align-items: end;
  gap: 0.45rem;
  min-height: 150px;
}

.trend-bar {
  flex: 1;
  display: grid;
  gap: 0.32rem;
  justify-items: center;
}

.trend-fill {
  width: 100%;
  max-width: 32px;
  border-radius: 8px 8px 2px 2px;
  background: linear-gradient(180deg, #4db2da, #3470ce);
  min-height: 6px;
}

.trend-bar span {
  font-size: 0.8rem;
}

.trend-bar small {
  color: var(--color-text-muted);
  font-size: 0.68rem;
}
</style>
