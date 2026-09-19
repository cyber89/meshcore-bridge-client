<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Repeater Detail</h1>
        <p class="section-subtitle" v-if="detail">
          {{ detail.node_name }} · {{ detail.status }} · last inform {{ formatTimestamp(detail.last_inform_at) }}
        </p>
      </div>
      <div class="header-actions">
        <router-link to="/repeaters" class="btn btn-secondary">Back to inventory</router-link>
        <button
          class="btn btn-primary"
          :disabled="loading || renewCertLoading || !canOperate"
          @click="queueCertRenewal"
        >
          {{ renewCertLoading ? "Queueing..." : "Renew Certificate" }}
        </button>
        <button
          class="btn btn-secondary"
          :disabled="loading || snapshotQueueLoading || !detail || !canOperate"
          @click="queueConfigSnapshotBackup"
        >
          {{ snapshotQueueLoading ? "Queueing backup..." : "Queue Config Backup" }}
        </button>
        <button class="btn btn-secondary" :disabled="loading" @click="loadDetail()">
          {{ loading ? "Loading..." : "Refresh detail" }}
        </button>
      </div>
    </header>

    <article v-if="errorMessage" class="glass-card panel">
      <h2>Unable to load repeater detail</h2>
      <p class="section-subtitle">{{ errorMessage }}</p>
    </article>

    <template v-else-if="detail">
      <section class="grid-3">
        <UiStatCard title="Location" :value="detail.location || '—'" />
        <UiStatCard
          title="Firmware / State"
          :value="detail.firmware_version || '—'"
          :subtitle="`state: ${detail.state || '—'}`"
        />
        <UiStatCard
          title="Live Stream"
          :value="appState.telemetryConnected ? 'connected' : 'disconnected'"
          :subtitle="`latest: ${latestLiveEvent ? formatTimestamp(latestLiveEvent.ingested_at) : '—'}`"
        />
      </section>

      <section class="grid-3">
        <article class="glass-card panel">
          <h2>Noise Floor Trend</h2>
          <p class="section-subtitle">
            Current: {{ formatDbm(currentNoiseFloor) }} · points: {{ noiseSeries.length }}
          </p>
          <svg v-if="noisePath" class="trend-svg" viewBox="0 0 900 240" role="img" aria-label="Noise floor trend">
            <rect x="0" y="0" width="900" height="240" class="trend-bg" />
            <path :d="noisePath" class="trend-line trend-noise" />
          </svg>
          <p v-else class="section-subtitle">No noise-floor history yet.</p>
        </article>

        <article class="glass-card panel">
          <h2>Airtime Trend</h2>
          <p class="section-subtitle">Current: {{ formatPercent(currentAirtime) }} · points: {{ airtimeSeries.length }}</p>
          <svg v-if="airtimePath" class="trend-svg" viewBox="0 0 900 240" role="img" aria-label="Airtime trend">
            <rect x="0" y="0" width="900" height="240" class="trend-bg" />
            <path :d="airtimePath" class="trend-line trend-airtime" />
          </svg>
          <p v-else class="section-subtitle">No airtime history yet.</p>
        </article>

        <article class="glass-card panel">
          <h2>Uptime Trend</h2>
          <p class="section-subtitle">Current: {{ formatUptime(currentUptime) }} · points: {{ uptimeSeries.length }}</p>
          <svg v-if="uptimePath" class="trend-svg" viewBox="0 0 900 240" role="img" aria-label="Uptime trend">
            <rect x="0" y="0" width="900" height="240" class="trend-bg" />
            <path :d="uptimePath" class="trend-line trend-uptime" />
          </svg>
          <p v-else class="section-subtitle">No uptime history yet.</p>
        </article>
      </section>

      <section class="grid-2">
        <article class="glass-card panel">
          <h2>Current System / Radio / Counters</h2>
          <div class="gauge-grid">
            <div v-for="metric in systemGaugeMetrics" :key="metric.key" class="gauge-card">
              <svg class="gauge-svg" viewBox="0 0 120 120" role="img" :aria-label="`${metric.label} gauge`">
                <circle class="gauge-track" cx="60" cy="60" r="44" />
                <circle
                  class="gauge-progress"
                  cx="60"
                  cy="60"
                  r="44"
                  :style="gaugeStyle(metric.value, metric.color)"
                />
                <text x="60" y="58" class="gauge-value">{{ formatPercent(metric.value) }}</text>
                <text x="60" y="76" class="gauge-label">{{ metric.label }}</text>
              </svg>
            </div>
          </div>
          <div class="metric-grid">
            <div class="metric-item">
              <span>Temperature</span>
              <strong>{{ formatTemp(fieldNumber(detail.system, "temperature_c")) }}</strong>
            </div>
            <div class="metric-item">
              <span>Uptime</span>
              <strong>{{ formatUptime(fieldNumber(detail.system, "uptime_seconds")) }}</strong>
            </div>
            <div class="metric-item">
              <span>Freq</span>
              <strong>{{ formatInt(fieldNumber(detail.radio, "frequency")) }}</strong>
            </div>
            <div class="metric-item">
              <span>SF</span>
              <strong>{{ formatInt(fieldNumber(detail.radio, "spreading_factor")) }}</strong>
            </div>
            <div class="metric-item">
              <span>RX / TX</span>
              <strong>
                {{ formatInt(fieldNumber(detail.counters, "rx_total")) }} / {{ formatInt(fieldNumber(detail.counters, "tx_total")) }}
              </strong>
            </div>
            <div class="metric-item">
              <span>Forwarded</span>
              <strong>{{ formatInt(fieldNumber(detail.counters, "forwarded")) }}</strong>
            </div>
            <div class="metric-item">
              <span>Dropped</span>
              <strong>{{ formatInt(fieldNumber(detail.counters, "dropped")) }}</strong>
            </div>
          </div>
        </article>

        <article class="glass-card panel">
          <h2>Latest Live Event</h2>
          <p class="section-subtitle" v-if="latestLiveEvent">
            {{ latestLiveEvent.topic }} · {{ formatTimestamp(latestLiveEvent.ingested_at) }}
          </p>
          <p class="section-subtitle" v-else>No live event seen for this repeater yet.</p>
          <pre class="json-block">{{ latestLivePayloadText }}</pre>
        </article>
      </section>


      <article class="glass-card panel">
        <div class="panel-header-inline">
          <h2>Encrypted Config Snapshots</h2>
          <button class="btn btn-secondary btn-sm" :disabled="snapshotLoading" @click="loadConfigSnapshots()">
            {{ snapshotLoading ? "Refreshing..." : "Refresh backups" }}
          </button>
        </div>
        <p class="section-subtitle">
          {{ configSnapshots.length }} snapshots stored for this repeater.
          <template v-if="latestSnapshotKeyId">
            Latest key ID: <code>{{ latestSnapshotKeyId }}</code>
          </template>
        </p>
        <p v-if="snapshotErrorMessage" class="section-subtitle">{{ snapshotErrorMessage }}</p>
        <UiDataTable v-else-if="configSnapshots.length">
          <thead>
            <tr>
              <th>Captured</th>
              <th>Size</th>
              <th>Key ID</th>
              <th>SHA-256</th>
              <th>Command</th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="snapshot in configSnapshots" :key="snapshot.id">
              <tr class="row-click" @click="toggleSnapshotExpanded(snapshot.id)">
                <td>{{ formatTimestamp(snapshot.captured_at) }}</td>
                <td>{{ formatBytes(snapshot.payload_size_bytes) }}</td>
                <td><code>{{ snapshot.encryption_key_id }}</code></td>
                <td><code>{{ formatShortHash(snapshot.payload_sha256) }}</code></td>
                <td><code>{{ snapshot.command_id || "—" }}</code></td>
                <td>
                  <button class="btn btn-secondary btn-sm" @click.stop="toggleSnapshotExpanded(snapshot.id)">
                    {{ isSnapshotExpanded(snapshot.id) ? "Hide" : "Show" }}
                  </button>
                </td>
              </tr>
              <tr v-if="isSnapshotExpanded(snapshot.id)">
                <td colspan="6">
                  <p v-if="isSnapshotDetailLoading(snapshot.id)" class="section-subtitle">Loading snapshot payload…</p>
                  <p v-else-if="snapshotDetailError(snapshot.id)" class="section-subtitle">
                    {{ snapshotDetailError(snapshot.id) }}
                  </p>
                  <pre v-else class="json-block">{{ formatSnapshotPayload(snapshot.id) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </UiDataTable>
        <p v-else class="section-subtitle">No encrypted config snapshots available yet.</p>
      </article>

      <article class="glass-card panel">
        <h2>Repeater Activity Logs</h2>
        <p class="section-subtitle">
          {{ certDiagnostics.length }} recent backend activity logs for this repeater.
        </p>
        <UiDataTable v-if="certDiagnostics.length">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Severity</th>
              <th>Source</th>
              <th>Message</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(entry, index) in certDiagnostics" :key="diagnosticRowKey(entry, index)">
              <tr class="row-click" @click="toggleDiagnosticExpanded(diagnosticRowKey(entry, index))">
                <td>{{ formatTimestamp(entry.timestamp) }}</td>
                <td>
                  <span class="diag-pill" :class="diagnosticSeverityClass(entry.severity)">
                    {{ entry.severity }}
                  </span>
                </td>
                <td><code>{{ entry.source }}</code></td>
                <td class="diag-message-cell">{{ entry.message }}</td>
                <td>
                  <button
                    class="btn btn-secondary btn-sm"
                    @click.stop="toggleDiagnosticExpanded(diagnosticRowKey(entry, index))"
                  >
                    {{ isDiagnosticExpanded(diagnosticRowKey(entry, index)) ? "Hide" : "Show" }}
                  </button>
                </td>
              </tr>
              <tr v-if="isDiagnosticExpanded(diagnosticRowKey(entry, index))">
                <td colspan="5">
                  <pre class="json-block diag-details">{{ formatDiagnosticDetails(entry.details) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </UiDataTable>
        <p v-else class="section-subtitle">No repeater activity logs available yet.</p>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";

import {
  ApiError,
  getConfigSnapshot,
  getRepeaterDetail,
  listConfigSnapshots,
  queueCommand,
  queueConfigSnapshotExport,
} from "../api";
import {
  appState,
  canOperate,
  formatTimestamp,
  showErrorToast,
  showSuccessToast,
} from "../state/appState";
import type {
  ConfigSnapshotDetailResponse,
  ConfigSnapshotResponse,
  MqttTelemetryEventResponse,
  RepeaterCertDiagnosticLogResponse,
  RepeaterDetailResponse,
} from "../types";

interface SeriesPoint {
  timestamp: string;
  value: number;
}

interface GaugeMetric {
  key: string;
  label: string;
  value: number | null;
  color: string;
}

function diagnosticRowKey(entry: RepeaterCertDiagnosticLogResponse, index: number): string {
  return `${entry.timestamp}-${entry.source}-${entry.message}-${index}`;
}

function isDiagnosticExpanded(key: string): boolean {
  return expandedDiagnosticRows.value.includes(key);
}

function toggleDiagnosticExpanded(key: string): void {
  if (isDiagnosticExpanded(key)) {
    expandedDiagnosticRows.value = expandedDiagnosticRows.value.filter((item) => item !== key);
    return;
  }
  expandedDiagnosticRows.value = [...expandedDiagnosticRows.value, key];
}

const route = useRoute();
const loading = ref(false);
const errorMessage = ref<string | null>(null);
const detail = ref<RepeaterDetailResponse | null>(null);
const renewCertLoading = ref(false);
const expandedDiagnosticRows = ref<string[]>([]);
const snapshotLoading = ref(false);
const snapshotQueueLoading = ref(false);
const snapshotErrorMessage = ref<string | null>(null);
const configSnapshots = ref<ConfigSnapshotResponse[]>([]);
const expandedSnapshotRows = ref<string[]>([]);
const snapshotDetailsById = ref<Record<string, ConfigSnapshotDetailResponse>>({});
const snapshotDetailErrorsById = ref<Record<string, string>>({});
const snapshotDetailLoadingIds = ref<string[]>([]);

const repeaterId = computed(() => String(route.params.repeaterId || ""));

const liveEvents = computed(() => {
  const current = detail.value;
  if (!current) {
    return [] as MqttTelemetryEventResponse[];
  }
  return appState.telemetryEvents.filter(
    (event) => event.repeater_id === current.id || event.node_name === current.node_name,
  );
});

const latestLiveEvent = computed(() => liveEvents.value[0] || null);
const certDiagnostics = computed<RepeaterCertDiagnosticLogResponse[]>(
  () => detail.value?.cert_diagnostics || [],
);
const latestSnapshotKeyId = computed(() => configSnapshots.value[0]?.encryption_key_id || null);

const latestLivePayloadText = computed(() => {
  if (!latestLiveEvent.value) {
    return "{}";
  }
  try {
    return JSON.stringify(latestLiveEvent.value.payload, null, 2);
  } catch {
    return "{}";
  }
});


const noiseSeries = computed<SeriesPoint[]>(() => {
  const points: SeriesPoint[] = [];
  for (const snapshot of detail.value?.snapshots || []) {
    if (typeof snapshot.noise_floor === "number") {
      points.push({ timestamp: snapshot.timestamp, value: snapshot.noise_floor });
    }
  }
  for (const event of liveEvents.value) {
    const payloadValue = fieldNumber(event.payload, "noise_floor_dbm");
    if (typeof payloadValue === "number") {
      points.push({ timestamp: event.timestamp, value: payloadValue });
    }
  }
  return sortSeries(points);
});
const uptimeSeries = computed<SeriesPoint[]>(() => {
  const points: SeriesPoint[] = [];
  for (const snapshot of detail.value?.snapshots || []) {
    if (typeof snapshot.uptime_seconds === "number") {
      points.push({ timestamp: snapshot.timestamp, value: snapshot.uptime_seconds });
    }
  }
  for (const event of liveEvents.value) {
    const payloadValue = fieldNumber(event.payload, "uptime_seconds");
    if (typeof payloadValue === "number") {
      points.push({ timestamp: event.timestamp, value: payloadValue });
    }
  }
  const systemUptime = fieldNumber(detail.value?.system, "uptime_seconds");
  if (typeof systemUptime === "number" && detail.value?.last_inform_at) {
    points.push({ timestamp: detail.value.last_inform_at, value: systemUptime });
  }
  return sortSeries(points);
});

const airtimeSeries = computed<SeriesPoint[]>(() => {
  const points: SeriesPoint[] = [];
  for (const snapshot of detail.value?.snapshots || []) {
    if (typeof snapshot.airtime_percent === "number") {
      points.push({ timestamp: snapshot.timestamp, value: snapshot.airtime_percent });
    }
  }
  for (const event of liveEvents.value) {
    const payloadValue = fieldNumber(event.payload, "utilization_percent");
    if (typeof payloadValue === "number") {
      points.push({ timestamp: event.timestamp, value: payloadValue });
    }
  }
  return sortSeries(points);
});

const currentNoiseFloor = computed(() => {
  const last = noiseSeries.value[noiseSeries.value.length - 1];
  return last ? last.value : null;
});

const currentAirtime = computed(() => {
  const last = airtimeSeries.value[airtimeSeries.value.length - 1];
  return last ? last.value : null;
});
const currentUptime = computed(() => {
  const last = uptimeSeries.value[uptimeSeries.value.length - 1];
  return last ? last.value : null;
});

const noisePath = computed(() => buildLinePath(noiseSeries.value, { minPadding: 2 }));
const airtimePath = computed(() => buildLinePath(airtimeSeries.value, { minPadding: 5 }));
const uptimePath = computed(() => buildLinePath(uptimeSeries.value));
const systemGaugeMetrics = computed<GaugeMetric[]>(() => [
  {
    key: "cpu",
    label: "CPU",
    value: fieldNumber(detail.value?.system, "cpu_percent"),
    color: "#62c8f8",
  },
  {
    key: "memory",
    label: "Memory",
    value: fieldNumber(detail.value?.system, "memory_percent"),
    color: "#67df9f",
  },
  {
    key: "disk",
    label: "Disk",
    value: fieldNumber(detail.value?.system, "disk_percent"),
    color: "#c996ff",
  },
]);

watch(repeaterId, () => {
  void loadDetail();
});

onMounted(() => {
  void loadDetail();
});

async function loadDetail(): Promise<void> {
  if (!appState.token || !repeaterId.value) {
    return;
  }
  loading.value = true;
  errorMessage.value = null;
  try {
    detail.value = await getRepeaterDetail(appState.token, repeaterId.value, {
      snapshot_limit: 360,
      cert_log_limit: 40,
    });
    expandedDiagnosticRows.value = [];
    await loadConfigSnapshots(detail.value.id);
  } catch (error) {
    configSnapshots.value = [];
    expandedSnapshotRows.value = [];
    snapshotDetailsById.value = {};
    snapshotDetailErrorsById.value = {};
    errorMessage.value = error instanceof Error ? error.message : "Failed loading repeater detail.";
  } finally {
    loading.value = false;
  }
}

async function queueCertRenewal(): Promise<void> {
  if (!appState.token || !detail.value || !canOperate.value) {
    return;
  }
  renewCertLoading.value = true;
  try {
    await queueCommand(appState.token, {
      node_name: detail.value.node_name,
      action: "rotate_cert",
      params: {},
      requested_by: appState.user?.email || "operator",
      reason: "Manual certificate renewal requested from repeater detail view",
    });
    showSuccessToast(
      "Certificate renewal command queued. The repeater will download a new cert on its next inform cycle.",
    );
  } catch (error) {
    showErrorToast(error);
  } finally {
    renewCertLoading.value = false;
  }
}

async function loadConfigSnapshots(targetRepeaterId?: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  const resolvedRepeaterId = targetRepeaterId || detail.value?.id;
  if (!resolvedRepeaterId) {
    return;
  }
  snapshotLoading.value = true;
  snapshotErrorMessage.value = null;
  try {
    const snapshots = await listConfigSnapshots(appState.token, {
      repeater_id: resolvedRepeaterId,
      limit: 100,
    });
    configSnapshots.value = snapshots;
    const validIds = new Set(snapshots.map((item) => item.id));
    expandedSnapshotRows.value = expandedSnapshotRows.value.filter((id) => validIds.has(id));
    snapshotDetailLoadingIds.value = snapshotDetailLoadingIds.value.filter((id) => validIds.has(id));
    snapshotDetailsById.value = Object.fromEntries(
      Object.entries(snapshotDetailsById.value).filter(([id]) => validIds.has(id)),
    ) as Record<string, ConfigSnapshotDetailResponse>;
    snapshotDetailErrorsById.value = Object.fromEntries(
      Object.entries(snapshotDetailErrorsById.value).filter(([id]) => validIds.has(id)),
    ) as Record<string, string>;
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      snapshotErrorMessage.value = "Config snapshot access requires admin/operator permissions.";
    } else {
      snapshotErrorMessage.value =
        error instanceof Error ? error.message : "Failed loading config snapshots.";
    }
  } finally {
    snapshotLoading.value = false;
  }
}

function isSnapshotExpanded(snapshotId: string): boolean {
  return expandedSnapshotRows.value.includes(snapshotId);
}

function isSnapshotDetailLoading(snapshotId: string): boolean {
  return snapshotDetailLoadingIds.value.includes(snapshotId);
}

async function toggleSnapshotExpanded(snapshotId: string): Promise<void> {
  if (isSnapshotExpanded(snapshotId)) {
    expandedSnapshotRows.value = expandedSnapshotRows.value.filter((id) => id !== snapshotId);
    return;
  }
  expandedSnapshotRows.value = [...expandedSnapshotRows.value, snapshotId];
  if (!snapshotDetailsById.value[snapshotId] && !isSnapshotDetailLoading(snapshotId)) {
    await loadSnapshotDetail(snapshotId);
  }
}

async function loadSnapshotDetail(snapshotId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  if (snapshotDetailsById.value[snapshotId] || isSnapshotDetailLoading(snapshotId)) {
    return;
  }
  snapshotDetailLoadingIds.value = [...snapshotDetailLoadingIds.value, snapshotId];
  delete snapshotDetailErrorsById.value[snapshotId];
  try {
    const snapshot = await getConfigSnapshot(appState.token, snapshotId);
    snapshotDetailsById.value = {
      ...snapshotDetailsById.value,
      [snapshotId]: snapshot,
    };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed loading snapshot payload details.";
    snapshotDetailErrorsById.value = {
      ...snapshotDetailErrorsById.value,
      [snapshotId]: message,
    };
  } finally {
    snapshotDetailLoadingIds.value = snapshotDetailLoadingIds.value.filter(
      (id) => id !== snapshotId,
    );
  }
}

async function queueConfigSnapshotBackup(): Promise<void> {
  if (!appState.token || !detail.value || !canOperate.value) {
    return;
  }
  snapshotQueueLoading.value = true;
  try {
    const queued = await queueConfigSnapshotExport(appState.token, {
      repeater_id: detail.value.id,
      reason: "Manual encrypted config backup requested from repeater detail view",
    });
    showSuccessToast(
      `Backup export queued (${queued.command_id}). Snapshot appears after the next successful export result.`,
    );
    await loadConfigSnapshots(detail.value.id);
  } catch (error) {
    showErrorToast(error);
  } finally {
    snapshotQueueLoading.value = false;
  }
}

function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number.parseFloat(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function fieldNumber(source: Record<string, unknown> | null | undefined, key: string): number | null {
  if (!source) {
    return null;
  }
  return numberFrom(source[key]);
}

function sortSeries(points: SeriesPoint[]): SeriesPoint[] {
  return [...points].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
}

function buildLinePath(points: SeriesPoint[], options?: { minPadding?: number }): string | null {
  if (points.length < 2) {
    return null;
  }
  const width = 900;
  const height = 240;
  const padding = 18;
  const minPadding = options?.minPadding ?? 0;
  const values = points.map((point) => point.value);
  const minValue = Math.min(...values) - minPadding;
  const maxValue = Math.max(...values) + minPadding;
  const span = maxValue - minValue || 1;
  const xStep = (width - padding * 2) / Math.max(1, points.length - 1);

  const coords = points.map((point, index) => {
    const x = padding + index * xStep;
    const normalized = (point.value - minValue) / span;
    const y = height - padding - normalized * (height - padding * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return `M${coords.join(" L")}`;
}

function formatPercent(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(1)}%`;
}

function formatDbm(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(1)} dBm`;
}


const gaugeRadius = 44;
const gaugeCircumference = 2 * Math.PI * gaugeRadius;

function gaugePercent(value: number | null): number {
  if (value === null) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function gaugeStyle(value: number | null, color: string): Record<string, string> {
  const percent = gaugePercent(value);
  const strokeDashoffset = gaugeCircumference * (1 - percent / 100);
  return {
    stroke: color,
    strokeDasharray: `${gaugeCircumference} ${gaugeCircumference}`,
    strokeDashoffset: `${strokeDashoffset}`,
  };
}
function formatInt(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return Math.round(value).toString();
}

function formatUptime(value: number | null): string {
  if (value === null) {
    return "—";
  }
  const totalSeconds = Math.max(0, Math.floor(value));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (days > 0) {
    return `${days}d ${hours}h ${minutes}m`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}


function formatTemp(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(1)}°C`;
}

function snapshotDetailError(snapshotId: string): string | null {
  return snapshotDetailErrorsById.value[snapshotId] || null;
}

function formatSnapshotPayload(snapshotId: string): string {
  const snapshot = snapshotDetailsById.value[snapshotId];
  if (!snapshot) {
    return "{}";
  }
  try {
    return JSON.stringify(snapshot.payload, null, 2);
  } catch {
    return "{}";
  }
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return "—";
  }
  if (value < 1024) {
    return `${Math.round(value)} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KiB`;
  }
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
}

function formatShortHash(value: string): string {
  if (!value || value.length <= 16) {
    return value || "—";
  }
  return `${value.slice(0, 8)}…${value.slice(-8)}`;
}
function formatDiagnosticDetails(details: Record<string, unknown>): string {
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return "{}";
  }
}

function diagnosticSeverityClass(severity: string): string {
  const normalized = severity.trim().toLowerCase();
  if (normalized === "error") {
    return "diag-error";
  }
  if (normalized === "warning") {
    return "diag-warning";
  }
  return "diag-info";
}
</script>

<style scoped>

.header-actions {
  display: flex;
  gap: 0.65rem;
}

.action-message {
  margin-top: -0.25rem;
}

.panel-header-inline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}

.trend-svg {
  width: 100%;
  height: auto;
  min-height: 210px;
}

.trend-bg {
  fill: #0a162a;
}

.trend-line {
  fill: none;
  stroke-width: 2.4;
}

.trend-noise {
  stroke: #62c8f8;
}

.trend-airtime {
  stroke: #67df9f;
}

.trend-uptime {
  stroke: #c996ff;
}

.gauge-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin-bottom: 0.8rem;
}

.gauge-card {
  border: 1px solid rgba(173, 193, 222, 0.22);
  border-radius: 10px;
  padding: 0.35rem;
  display: flex;
  justify-content: center;
}

.gauge-svg {
  width: 120px;
  height: 120px;
}

.gauge-track {
  fill: none;
  stroke: rgba(173, 193, 222, 0.22);
  stroke-width: 10;
}

.gauge-progress {
  fill: none;
  stroke-width: 10;
  transform: rotate(-90deg);
  transform-origin: 60px 60px;
  stroke-linecap: round;
}

.gauge-value {
  fill: #e9f2ff;
  font-size: 12px;
  font-weight: 700;
  text-anchor: middle;
}

.gauge-label {
  fill: #9fb6d7;
  font-size: 10px;
  text-anchor: middle;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.55rem;
}

.metric-item {
  border: 1px solid rgba(173, 193, 222, 0.22);
  border-radius: 8px;
  padding: 0.5rem 0.65rem;
  display: grid;
  gap: 0.15rem;
}

.metric-item span {
  color: var(--color-text-muted);
  font-size: 0.74rem;
}

.metric-item strong {
  font-size: 0.94rem;
}

.json-block {
  margin: 0;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: #0b1422;
  border-radius: 8px;
  border: 1px solid rgba(173, 193, 222, 0.2);
  padding: 0.75rem;
  font-size: 0.8rem;
}


.diag-pill {
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border: 1px solid transparent;
}

.diag-info {
  background: rgba(98, 200, 248, 0.15);
  border-color: rgba(98, 200, 248, 0.45);
  color: #9edfff;
}

.diag-warning {
  background: rgba(248, 196, 69, 0.15);
  border-color: rgba(248, 196, 69, 0.45);
  color: #ffd894;
}

.diag-error {
  background: rgba(237, 79, 79, 0.18);
  border-color: rgba(237, 79, 79, 0.5);
  color: #ffb8b8;
}

.diag-details {
  max-height: 180px;
}

.diag-message-cell {
  max-width: 420px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 740px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .gauge-grid {
    grid-template-columns: 1fr;
  }

  .panel-header-inline {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
