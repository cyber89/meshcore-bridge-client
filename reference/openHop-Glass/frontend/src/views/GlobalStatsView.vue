<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Global Stats</h1>
        <p class="section-subtitle">
          Fleet-wide packet analytics across all repeaters, including distribution and recent packet traffic.
        </p>
      </div>
      <div class="toolbar">
        <label class="field-label">
          Time range
          <select v-model.number="selectedHours" class="field-select">
            <option v-for="option in timeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <button class="btn btn-secondary" :disabled="loading" @click="loadData()">
          {{ loading ? "Refreshing..." : "Refresh" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <section class="grid-3">
      <UiStatCard title="Total Packets" :value="summary?.total_packets ?? 0" />
      <UiStatCard title="Active Repeaters" :value="summary?.unique_repeaters ?? 0" />
      <UiStatCard title="Unique Sources" :value="summary?.unique_sources ?? 0" />
      <UiStatCard title="Unique Destinations" :value="summary?.unique_destinations ?? 0" />
      <UiStatCard title="Average RSSI" :value="formatSignal(summary?.avg_rssi, 'dBm')" />
      <UiStatCard title="Average SNR" :value="formatSignal(summary?.avg_snr, 'dB')" />
    </section>

    <section class="grid-2">
      <UiPanelCard title="Packet Type Distribution" subtitle="Message volume by packet type.">
        <p v-if="packetTypeBars.length === 0" class="section-subtitle">No packet activity in this time range.</p>
        <div v-else class="bar-stack">
          <div v-for="bar in packetTypeBars" :key="bar.key" class="bar-row">
            <div class="bar-label">
              <span class="pill pill-gray">{{ bar.key }}</span>
              <span>{{ bar.count }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill type-fill" :style="{ width: `${bar.percent}%` }" />
            </div>
          </div>
        </div>
      </UiPanelCard>

      <UiPanelCard title="Route Distribution" subtitle="Traffic segmented by route class.">
        <p v-if="routeBars.length === 0" class="section-subtitle">No route data in this time range.</p>
        <div v-else class="bar-stack">
          <div v-for="bar in routeBars" :key="bar.key" class="bar-row">
            <div class="bar-label">
              <span class="pill pill-gray">{{ bar.key }}</span>
              <span>{{ bar.count }}</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill route-fill" :style="{ width: `${bar.percent}%` }" />
            </div>
          </div>
        </div>
      </UiPanelCard>
    </section>

    <UiPanelCard title="Packet Volume Trend" :subtitle="`Grouped over the last ${selectedHours}h.`">
      <p v-if="packetTrend.length === 0" class="section-subtitle">No packet trend data available.</p>
      <div v-else class="trend-chart">
        <div v-for="point in packetTrend" :key="point.label" class="trend-bar">
          <div class="trend-fill" :style="{ height: `${point.percent}%` }" />
          <span>{{ point.count }}</span>
          <small>{{ point.label }}</small>
        </div>
      </div>
    </UiPanelCard>

    <UiPanelCard title="All Repeaters Packet Table" subtitle="Latest packets across the whole fleet.">
      <div class="table-header">
        <p class="section-subtitle">
          Showing {{ pageStart }}–{{ pageEnd }} of {{ filteredPackets.length }} packets
        </p>
        <button class="btn btn-ghost btn-sm" @click="resetFilters()">Reset filters</button>
      </div>
      <div class="table-filters">
        <label class="field-label">
          Node
          <select v-model="nodeFilter" class="field-select">
            <option value="all">All nodes</option>
            <option v-for="name in availableNodes" :key="name" :value="name">
              {{ name }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Type
          <select v-model="typeFilter" class="field-select">
            <option value="all">All packet types</option>
            <option v-for="value in availablePacketTypes" :key="value.raw" :value="value.raw">
              {{ value.label }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Route
          <select v-model="routeFilter" class="field-select">
            <option value="all">All routes</option>
            <option v-for="value in availableRoutes" :key="value.raw" :value="value.raw">
              {{ value.label }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Rows
          <select v-model.number="itemsPerPage" class="field-select">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
          </select>
        </label>
      </div>

      <UiDataTable>
        <thead>
          <tr>
            <th>Time</th>
            <th>Node</th>
            <th>Type</th>
            <th>Route</th>
            <th>RSSI</th>
            <th>SNR</th>
            <th>Source</th>
            <th>Destination</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="packet in paginatedPackets" :key="packet.id">
            <td>{{ formatTimestamp(packet.timestamp) }}</td>
            <td>{{ packet.node_name }}</td>
            <td>{{ formatPacketType(packet.packet_type) }}</td>
            <td>{{ formatRoute(packet.route) }}</td>
            <td>{{ packet.rssi == null ? "—" : packet.rssi.toFixed(1) }}</td>
            <td>{{ packet.snr == null ? "—" : packet.snr.toFixed(1) }}</td>
            <td><code>{{ packet.src_hash || "—" }}</code></td>
            <td><code>{{ packet.dst_hash || "—" }}</code></td>
            <td class="payload">{{ packet.payload || "—" }}</td>
          </tr>
          <tr v-if="!loading && filteredPackets.length === 0">
            <td colspan="9" class="section-subtitle">No packets match the selected filters.</td>
          </tr>
          <tr v-if="loading">
            <td colspan="9" class="section-subtitle">Loading packets...</td>
          </tr>
        </tbody>
      </UiDataTable>

      <div v-if="totalPages > 1" class="pagination-row">
        <button class="btn btn-ghost btn-sm" :disabled="currentPage <= 1" @click="currentPage -= 1">
          Previous
        </button>
        <div class="pagination-pages">
          <button
            v-for="page in visiblePages"
            :key="page"
            class="btn btn-sm"
            :class="page === currentPage ? 'btn-secondary' : 'btn-ghost'"
            @click="currentPage = page"
          >
            {{ page }}
          </button>
        </div>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="currentPage >= totalPages"
          @click="currentPage += 1"
        >
          Next
        </button>
      </div>
    </UiPanelCard>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import { getPacketSummary, listPackets } from "../api";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import { appState, formatTimestamp } from "../state/appState";
import type { PacketRecordResponse, PacketSummaryResponse } from "../types";

const selectedHours = ref(24);
const loading = ref(false);
const error = ref<string | null>(null);
const summary = ref<PacketSummaryResponse | null>(null);
const packets = ref<PacketRecordResponse[]>([]);
const nodeFilter = ref("all");
const typeFilter = ref("all");
const routeFilter = ref("all");
const currentPage = ref(1);
const itemsPerPage = ref(10);

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

const timeOptions = [
  { value: 1, label: "1 hour" },
  { value: 6, label: "6 hours" },
  { value: 24, label: "24 hours" },
  { value: 48, label: "2 days" },
  { value: 168, label: "7 days" },
];

const availableNodes = computed(() =>
  Array.from(new Set(packets.value.map((item) => item.node_name))).sort(),
);
const availablePacketTypes = computed(() =>
  Array.from(new Set(packets.value.map((item) => item.packet_type || "unknown")))
    .sort()
    .map((raw) => ({ raw, label: formatPacketType(raw) })),
);
const availableRoutes = computed(() =>
  Array.from(new Set(packets.value.map((item) => item.route || "unknown")))
    .sort()
    .map((raw) => ({ raw, label: formatRoute(raw) })),
);

const filteredPackets = computed(() =>
  packets.value.filter((packet) => {
    if (nodeFilter.value !== "all" && packet.node_name !== nodeFilter.value) {
      return false;
    }
    const resolvedType = packet.packet_type || "unknown";
    if (typeFilter.value !== "all" && resolvedType !== typeFilter.value) {
      return false;
    }
    const resolvedRoute = packet.route || "unknown";
    if (routeFilter.value !== "all" && resolvedRoute !== routeFilter.value) {
      return false;
    }
    return true;
  }),
);
const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredPackets.value.length / itemsPerPage.value)),
);
const paginatedPackets = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value;
  return filteredPackets.value.slice(start, start + itemsPerPage.value);
});
const pageStart = computed(() => {
  if (filteredPackets.value.length === 0) {
    return 0;
  }
  return (currentPage.value - 1) * itemsPerPage.value + 1;
});
const pageEnd = computed(() =>
  Math.min(currentPage.value * itemsPerPage.value, filteredPackets.value.length),
);
const visiblePages = computed(() => {
  const start = Math.max(1, currentPage.value - 2);
  const end = Math.min(totalPages.value, currentPage.value + 2);
  const pages: number[] = [];
  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }
  return pages;
});

const packetTypeBars = computed(() => toBars(summary.value?.by_packet_type ?? {}, formatPacketType));
const routeBars = computed(() => toBars(summary.value?.by_route ?? {}, formatRoute));

const packetTrend = computed(() => {
  const bucketHours = selectedHours.value > 72 ? 6 : selectedHours.value > 24 ? 3 : 1;
  const bucketMs = bucketHours * 60 * 60 * 1000;
  const grouped = new Map<number, number>();
  for (const packet of packets.value) {
    const ts = new Date(packet.timestamp).getTime();
    if (Number.isNaN(ts)) {
      continue;
    }
    const bucket = Math.floor(ts / bucketMs) * bucketMs;
    grouped.set(bucket, (grouped.get(bucket) ?? 0) + 1);
  }
  const entries = Array.from(grouped.entries()).sort((a, b) => a[0] - b[0]);
  const max = Math.max(1, ...entries.map(([, count]) => count));
  return entries.map(([bucket, count]) => ({
    label: new Date(bucket).toISOString().slice(5, 16).replace("T", " "),
    count,
    percent: Math.max(6, Math.round((count / max) * 100)),
  }));
});

watch(selectedHours, async () => {
  currentPage.value = 1;
  await loadData();
});
watch([nodeFilter, typeFilter, routeFilter, itemsPerPage], () => {
  currentPage.value = 1;
});
watch(totalPages, (nextTotal) => {
  if (currentPage.value > nextTotal) {
    currentPage.value = nextTotal;
  }
});

watch(
  () => appState.token,
  async (token) => {
    if (token) {
      await loadData();
    }
  },
);

onMounted(async () => {
  await loadData();
});

async function loadData(): Promise<void> {
  if (!appState.token) {
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const [summaryResponse, packetResponse] = await Promise.all([
      getPacketSummary(appState.token, { hours: selectedHours.value }),
      listPackets(appState.token, { hours: selectedHours.value, limit: 500 }),
    ]);
    summary.value = summaryResponse;
    packets.value = packetResponse;
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : "Failed to load global packet stats.";
    error.value = message;
  } finally {
    loading.value = false;
  }
}

function toBars(
  input: Record<string, number>,
  formatter: (value: string | null | undefined) => string,
): Array<{ key: string; count: number; percent: number }> {
  const rows = Object.entries(input).map(([key, count]) => ({ key, count }));
  if (rows.length === 0) {
    return [];
  }
  const max = Math.max(1, ...rows.map((item) => item.count));
  return rows
    .sort((a, b) => b.count - a.count)
    .map((item) => ({
      ...item,
      key: formatter(item.key),
      percent: Math.max(8, Math.round((item.count / max) * 100)),
    }));
}

function formatSignal(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return "—";
  }
  return `${value.toFixed(1)} ${unit}`;
}

function formatPacketType(raw: string | null | undefined): string {
  const key = (raw || "unknown").trim();
  if (!key || key === "unknown") {
    return "Unknown";
  }
  if (PACKET_TYPE_LABELS[key]) {
    return `${key} · ${PACKET_TYPE_LABELS[key]}`;
  }
  return formatTokenLabel(key);
}

function formatRoute(raw: string | null | undefined): string {
  const key = (raw || "unknown").trim();
  if (!key || key === "unknown") {
    return "Unknown";
  }
  if (ROUTE_LABELS[key]) {
    return `${key} · ${ROUTE_LABELS[key]}`;
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


function resetFilters(): void {
  nodeFilter.value = "all";
  typeFilter.value = "all";
  routeFilter.value = "all";
  itemsPerPage.value = 10;
}
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: end;
}

.toolbar .field-label {
  min-width: 150px;
}

.error-text {
  color: #fb787b;
  font-size: 0.88rem;
}

.table-filters {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
}

.table-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
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

.type-fill {
  background: linear-gradient(90deg, #7e62e6, #a986f8);
}

.route-fill {
  background: linear-gradient(90deg, #1d9a93, #60d8cb);
}

.trend-chart {
  display: flex;
  align-items: end;
  gap: 0.45rem;
  min-height: 160px;
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

.trend-bar {
  min-width: 28px;
  display: grid;
  gap: 0.32rem;
  justify-items: center;
}

.trend-fill {
  width: 100%;
  border-radius: 8px 8px 2px 2px;
  background: linear-gradient(180deg, #4db2da, #3470ce);
  min-height: 6px;
}

.trend-bar span {
  font-size: 0.74rem;
}

.trend-bar small {
  color: var(--color-text-muted);
  font-size: 0.63rem;
  transform: rotate(-38deg);
  transform-origin: center;
  white-space: nowrap;
}

.payload {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination-row {
  margin-top: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.pagination-pages {
  display: flex;
  gap: 0.35rem;
}
</style>
