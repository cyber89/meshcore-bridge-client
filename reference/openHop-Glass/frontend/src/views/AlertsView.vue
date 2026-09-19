<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Alerts</h1>
        <p class="section-subtitle">
          Monitor active conditions, track notification delivery, and manage alert lifecycle state.
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="loading" @click="refreshData()">
        {{ loading ? "Refreshing..." : "Refresh" }}
      </button>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <section class="grid-3">
      <UiStatCard title="Total Alerts" :value="summary?.total ?? 0" />
      <UiStatCard title="Active" :value="summary?.active ?? 0" />
      <UiStatCard title="Acknowledged" :value="summary?.acknowledged ?? 0" />
      <UiStatCard title="Suppressed" :value="summary?.suppressed ?? 0" />
      <UiStatCard title="Resolved" :value="summary?.resolved ?? 0" />
      <UiStatCard title="Critical" :value="summary?.by_severity?.critical ?? 0" />
    </section>

    <UiPanelCard title="Filters" subtitle="Refine the alert list by lifecycle, severity, type, and node.">
      <form class="filter-grid" @submit.prevent="applyFilters()">
        <label class="field-label">
          State
          <select v-model="filters.state" class="field-select">
            <option value="all">All states</option>
            <option v-for="state in stateOptions" :key="state" :value="state">
              {{ formatTokenLabel(state) }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Severity
          <select v-model="filters.severity" class="field-select">
            <option value="all">All severities</option>
            <option v-for="severity in availableSeverities" :key="severity" :value="severity">
              {{ formatTokenLabel(severity) }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Alert type
          <select v-model="filters.alertType" class="field-select">
            <option value="all">All alert types</option>
            <option v-for="alertType in availableAlertTypes" :key="alertType" :value="alertType">
              {{ formatTokenLabel(alertType) }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Node
          <select v-model="filters.nodeName" class="field-select">
            <option value="all">All nodes</option>
            <option v-for="node in availableNodes" :key="node" :value="node">
              {{ node }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Search
          <input
            v-model.trim="filters.search"
            class="field"
            placeholder="message / type / node / fingerprint"
          />
        </label>
        <label class="field-label">
          Rows
          <select v-model.number="itemsPerPage" class="field-select">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
          </select>
        </label>
        <div class="filter-actions">
          <button class="btn btn-secondary">Apply</button>
          <button class="btn btn-ghost" type="button" @click="resetFilters()">Reset</button>
        </div>
      </form>
    </UiPanelCard>

    <UiPanelCard title="Alert List" :subtitle="`Showing ${pagedRangeStart}-${pagedRangeEnd} of ${filteredAlerts.length} matching alerts`">
        <UiDataTable>
          <thead>
            <tr>
              <th>Last Seen</th>
              <th>Node</th>
              <th>Type</th>
              <th>Severity</th>
              <th>State</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="alert in paginatedAlerts"
              :key="alert.id"
              class="row-click"
              :class="{ selected: selectedAlertId === alert.id }"
              @click="selectAlert(alert.id)"
            >
              <td>{{ formatTimestamp(alert.last_seen_at) }}</td>
              <td>{{ alert.node_name || "—" }}</td>
              <td>{{ formatTokenLabel(alert.alert_type) }}</td>
              <td>
                <span class="pill" :class="severityPillClass(alert.severity)">
                  {{ formatTokenLabel(alert.severity) }}
                </span>
              </td>
              <td><StatusPill :status="alert.state" /></td>
              <td class="message-cell">{{ alert.message }}</td>
            </tr>
            <tr v-if="!loading && filteredAlerts.length === 0">
              <td colspan="6" class="section-subtitle">No alerts match the selected filters.</td>
            </tr>
            <tr v-if="loading">
              <td colspan="6" class="section-subtitle">Loading alerts...</td>
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
    <Teleport to="body">
      <div v-if="selectedAlertId" class="alert-dialog-backdrop" @click.self="closeDetailDialog()">
        <section class="alert-dialog" role="dialog" aria-modal="true" aria-label="Alert detail">
          <header class="dialog-header">
            <div>
              <h2 class="dialog-title">Alert Detail</h2>
              <p class="section-subtitle">{{ selectedAlert ? formatTokenLabel(selectedAlert.alert_type) : "Loading..." }}</p>
            </div>
            <button class="btn btn-ghost btn-sm" @click="closeDetailDialog()">Close</button>
          </header>
          <div class="dialog-body">
        <p v-if="!canOperate" class="section-subtitle">Viewer accounts can inspect alerts but cannot mutate state.</p>
        <template v-if="selectedAlert">
          <div class="detail-grid">
            <div>
              <p class="detail-label">Type</p>
              <p>{{ formatTokenLabel(selectedAlert.alert_type) }}</p>
            </div>
            <div>
              <p class="detail-label">Severity</p>
              <span class="pill" :class="severityPillClass(selectedAlert.severity)">
                {{ formatTokenLabel(selectedAlert.severity) }}
              </span>
            </div>
            <div>
              <p class="detail-label">Node</p>
              <p>{{ selectedAlert.node_name || "—" }}</p>
            </div>
            <div>
              <p class="detail-label">State</p>
              <StatusPill :status="selectedAlert.state" />
            </div>
            <div>
              <p class="detail-label">First Seen</p>
              <p>{{ formatTimestamp(selectedAlert.first_seen_at) }}</p>
            </div>
            <div>
              <p class="detail-label">Last Seen</p>
              <p>{{ formatTimestamp(selectedAlert.last_seen_at) }}</p>
            </div>
            <div>
              <p class="detail-label">Acknowledged</p>
              <p>{{ formatTimestamp(selectedAlert.acked_at) }}</p>
            </div>
            <div>
              <p class="detail-label">Resolved</p>
              <p>{{ formatTimestamp(selectedAlert.resolved_at) }}</p>
            </div>
          </div>

          <div class="message-block">
            <p class="detail-label">Message</p>
            <p>{{ selectedAlert.message }}</p>
          </div>

          <div class="message-block">
            <p class="detail-label">Fingerprint</p>
            <code>{{ selectedAlert.fingerprint || "—" }}</code>
          </div>

          <label class="field-label">
            Operator note
            <textarea
              v-model.trim="lifecycleNote"
              class="field-textarea"
              placeholder="Optional note to include with lifecycle updates"
            />
          </label>

          <div class="actions-row">
            <button
              class="btn btn-secondary btn-sm"
              :disabled="!canAcknowledge"
              @click="updateAlertState('acknowledge')"
            >
              {{ actionLoading ? "Saving..." : "Acknowledge" }}
            </button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!canResolve"
              @click="updateAlertState('resolve')"
            >
              {{ actionLoading ? "Saving..." : "Resolve" }}
            </button>
            <button
              class="btn btn-ghost btn-sm"
              :disabled="!canSuppress"
              @click="updateAlertState('suppress')"
            >
              {{ actionLoading ? "Saving..." : "Suppress" }}
            </button>
          </div>

          <h3 class="detail-heading">Notification Events</h3>
          <UiDataTable>
            <thead>
              <tr>
                <th>Created</th>
                <th>Channel</th>
                <th>Event</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Delivery</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="event in selectedAlert.notifications" :key="event.id">
                <td>{{ formatTimestamp(event.created_at) }}</td>
                <td>{{ event.channel }}</td>
                <td>{{ formatTokenLabel(event.event_type) }}</td>
                <td><StatusPill :status="event.status" /></td>
                <td>{{ event.attempts }}</td>
                <td>
                  <p>{{ formatTimestamp(event.sent_at || event.next_attempt_at) }}</p>
                  <small v-if="event.last_error" class="error-text">{{ event.last_error }}</small>
                </td>
              </tr>
              <tr v-if="!detailLoading && selectedAlert.notifications.length === 0">
                <td colspan="6" class="section-subtitle">No notification events recorded for this alert.</td>
              </tr>
              <tr v-if="detailLoading">
                <td colspan="6" class="section-subtitle">Loading alert detail...</td>
              </tr>
            </tbody>
          </UiDataTable>
        </template>
        <p v-else-if="detailLoading" class="section-subtitle">Loading alert detail...</p>
        <p v-else class="section-subtitle">Select an alert row to view detail and notification events.</p>
          </div>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import {
  acknowledgeAlert,
  getAlertDetail,
  getAlertSummary,
  listAlerts,
  resolveAlert,
  suppressAlert,
} from "../api";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import StatusPill from "../components/ui/StatusPill.vue";
import { appState, canOperate, formatTimestamp } from "../state/appState";
import type { AlertDetailResponse, AlertResponse, AlertSummaryResponse } from "../types";

const stateOptions = ["active", "acknowledged", "suppressed", "resolved"];

const loading = ref(false);
const detailLoading = ref(false);
const actionLoading = ref(false);
const error = ref<string | null>(null);

const summary = ref<AlertSummaryResponse | null>(null);
const alerts = ref<AlertResponse[]>([]);
const selectedAlertId = ref<string | null>(null);
const selectedAlert = ref<AlertDetailResponse | null>(null);
const lifecycleNote = ref("");

const filters = reactive({
  state: "all",
  severity: "all",
  alertType: "all",
  nodeName: "all",
  search: "",
});

const itemsPerPage = ref(10);
const currentPage = ref(1);

const availableSeverities = computed(() => {
  const values = new Set<string>();
  for (const alert of alerts.value) {
    values.add(alert.severity);
  }
  for (const severity of Object.keys(summary.value?.by_severity ?? {})) {
    values.add(severity);
  }
  return Array.from(values).sort();
});

const availableAlertTypes = computed(() =>
  Array.from(new Set(alerts.value.map((alert) => alert.alert_type))).sort(),
);

const availableNodes = computed(() => {
  const values = new Set<string>();
  for (const repeater of appState.repeaters) {
    values.add(repeater.node_name);
  }
  for (const alert of alerts.value) {
    if (alert.node_name) {
      values.add(alert.node_name);
    }
  }
  return Array.from(values).sort();
});

const filteredAlerts = computed(() => {
  const query = filters.search.trim().toLowerCase();
  if (!query) {
    return alerts.value;
  }
  return alerts.value.filter((alert) => {
    const stack = [
      alert.alert_type,
      alert.severity,
      alert.state,
      alert.message,
      alert.node_name || "",
      alert.fingerprint || "",
    ]
      .join(" ")
      .toLowerCase();
    return stack.includes(query);
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredAlerts.value.length / itemsPerPage.value)));
const paginatedAlerts = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value;
  return filteredAlerts.value.slice(start, start + itemsPerPage.value);
});
const pagedRangeStart = computed(() => {
  if (filteredAlerts.value.length === 0) {
    return 0;
  }
  return (currentPage.value - 1) * itemsPerPage.value + 1;
});
const pagedRangeEnd = computed(() =>
  filteredAlerts.value.length === 0
    ? 0
    : Math.min(currentPage.value * itemsPerPage.value, filteredAlerts.value.length),
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

const canAcknowledge = computed(() => {
  if (!canOperate.value || actionLoading.value || !selectedAlert.value) {
    return false;
  }
  return !["acknowledged", "resolved"].includes(selectedAlert.value.state);
});

const canResolve = computed(() => {
  if (!canOperate.value || actionLoading.value || !selectedAlert.value) {
    return false;
  }
  return selectedAlert.value.state !== "resolved";
});

const canSuppress = computed(() => {
  if (!canOperate.value || actionLoading.value || !selectedAlert.value) {
    return false;
  }
  return selectedAlert.value.state !== "suppressed";
});

watch(
  () => appState.token,
  async (token) => {
    if (token) {
      await refreshData();
    }
  },
);

watch([() => filters.search, itemsPerPage], () => {
  currentPage.value = 1;
});

watch(totalPages, (nextTotal) => {
  if (currentPage.value > nextTotal) {
    currentPage.value = nextTotal;
  }
});

onMounted(async () => {
  await refreshData();
  window.addEventListener("keydown", handleEscapeKey);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleEscapeKey);
});

async function refreshData(): Promise<void> {
  await Promise.all([loadSummary(), loadAlerts()]);
}

async function loadSummary(): Promise<void> {
  if (!appState.token) {
    return;
  }
  try {
    summary.value = await getAlertSummary(appState.token);
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to load alert summary.";
  }
}

async function loadAlerts(): Promise<void> {
  if (!appState.token) {
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    alerts.value = await listAlerts(appState.token, {
      state: resolveFilter(filters.state),
      severity: resolveFilter(filters.severity),
      alert_type: resolveFilter(filters.alertType),
      node_name: resolveFilter(filters.nodeName),
      limit: 500,
      offset: 0,
    });
    if (selectedAlertId.value && !alerts.value.some((item) => item.id === selectedAlertId.value)) {
      selectedAlertId.value = null;
      selectedAlert.value = null;
      lifecycleNote.value = "";
    }
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : "Failed to load alerts.";
    error.value = message;
  } finally {
    loading.value = false;
  }
}

async function applyFilters(): Promise<void> {
  currentPage.value = 1;
  await loadAlerts();
}

async function selectAlert(alertId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  selectedAlertId.value = alertId;
  detailLoading.value = true;
  try {
    const detail = await getAlertDetail(appState.token, alertId);
    selectedAlert.value = detail;
    lifecycleNote.value = detail.note ?? "";
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to load alert detail.";
  } finally {
    detailLoading.value = false;
  }
}

async function updateAlertState(action: "acknowledge" | "resolve" | "suppress"): Promise<void> {
  if (!appState.token || !selectedAlertId.value) {
    return;
  }
  actionLoading.value = true;
  try {
    const payload = { note: lifecycleNote.value || undefined };
    if (action === "acknowledge") {
      await acknowledgeAlert(appState.token, selectedAlertId.value, payload);
    } else if (action === "resolve") {
      await resolveAlert(appState.token, selectedAlertId.value, payload);
    } else {
      await suppressAlert(appState.token, selectedAlertId.value, payload);
    }
    const actionLabel =
      action === "acknowledge" ? "acknowledged" : action === "resolve" ? "resolved" : "suppressed";
    appState.toastSuccess = `Alert ${actionLabel} successfully.`;
    appState.toastError = null;
    await Promise.all([loadSummary(), loadAlerts(), selectAlert(selectedAlertId.value)]);
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to update alert state.";
  } finally {
    actionLoading.value = false;
  }
}

function resetFilters(): void {
  filters.state = "all";
  filters.severity = "all";
  filters.alertType = "all";
  filters.nodeName = "all";
  filters.search = "";
  itemsPerPage.value = 10;
  currentPage.value = 1;
  void loadAlerts();
}

function closeDetailDialog(): void {
  selectedAlertId.value = null;
  selectedAlert.value = null;
  lifecycleNote.value = "";
}

function handleEscapeKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && selectedAlertId.value) {
    closeDetailDialog();
  }
}

function resolveFilter(value: string): string | undefined {
  return value === "all" ? undefined : value;
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

function severityPillClass(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === "critical") {
    return "pill-red";
  }
  if (normalized === "warning") {
    return "pill-amber";
  }
  if (normalized === "info" || normalized === "notice") {
    return "pill-gray";
  }
  return "pill-gray";
}
</script>

<style scoped>
.error-text {
  color: #fb787b;
  font-size: 0.88rem;
}

.filter-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.filter-actions {
  display: flex;
  gap: 0.5rem;
  align-items: end;
}

.message-cell {
  max-width: 280px;
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
.alert-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2400;
  background: rgba(6, 11, 20, 0.58);
  display: grid;
  place-items: center;
  padding: 1.5rem;
}
.alert-dialog {
  width: min(920px, 94vw);
  max-height: min(84vh, 900px);
  background: rgba(6, 11, 20, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  backdrop-filter: blur(20px);
  box-shadow: 0 22px 44px rgba(0, 0, 0, 0.4);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.9rem 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.dialog-title {
  margin: 0;
  font-size: 1.05rem;
}
.dialog-body {
  padding: 0.95rem 1rem 1rem;
  display: grid;
  gap: 0.75rem;
  overflow-y: auto;
}

.detail-grid {
  display: grid;
  gap: 0.8rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.detail-label {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  margin-bottom: 0.22rem;
}

.message-block {
  display: grid;
  gap: 0.25rem;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.detail-heading {
  margin-top: 0.35rem;
  font-size: 0.9rem;
}

@media (max-width: 760px) {
  .alert-dialog-backdrop {
    padding: 0.6rem;
  }
  .alert-dialog {
    width: 98vw;
    max-height: 90vh;
  }
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
