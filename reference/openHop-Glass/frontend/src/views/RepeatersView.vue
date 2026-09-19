<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Repeater Inventory</h1>
        <p class="section-subtitle">
          Manage repeaters from one table and run bulk actions like restart, cert rotation, or config updates.
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshAllData()">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh" }}
      </button>
    </header>

    <section class="grid-2">
      <article class="glass-card panel">
        <h2>Bulk Repeater Actions</h2>
        <p class="section-subtitle">
          {{ selectedCount }} selected · queue one action across selected repeaters.
        </p>
        <form class="panel-form" @submit.prevent="queueBulkAction">
          <label class="field-label">
            Action
            <select v-model="bulkForm.action" class="field-select" :disabled="!canOperate">
              <option v-for="action in COMMAND_ACTIONS" :key="action" :value="action">
                {{ action }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Reason
            <input
              v-model.trim="bulkForm.reason"
              class="field"
              :disabled="!canOperate"
              placeholder="Optional reason for audit log"
            />
          </label>
          <label class="field-label">
            Params JSON
            <textarea
              v-model="bulkForm.paramsJson"
              class="field-textarea"
              :disabled="!canOperate"
              placeholder='{"key":"value"}'
            />
          </label>
          <div class="inline-controls">
            <button
              class="btn btn-primary"
              :disabled="!canOperate || appState.actionLoading || selectedCount === 0"
            >
              {{ appState.actionLoading ? "Queueing..." : "Queue action to selected" }}
            </button>
            <button
              type="button"
              class="btn btn-secondary"
              :disabled="selectedCount === 0"
              @click="clearSelection"
            >
              Clear selection
            </button>
          </div>
        </form>
      </article>

      <article class="glass-card panel">
        <h2>Stale Repeater Cleanup</h2>
        <p class="section-subtitle">
          {{ staleCount }} repeaters are currently older than the inactivity threshold.
        </p>
        <div class="inline-controls">
          <label class="field-label">
            Inactive hours
            <input v-model.number="staleHours" class="field" type="number" min="1" max="8760" />
          </label>
          <button class="btn btn-primary" :disabled="!canOperate || appState.actionLoading" @click="removeStale">
            {{ appState.actionLoading ? "Removing..." : "Remove stale repeaters" }}
          </button>
        </div>
      </article>
    </section>

    <article class="glass-card panel">
      <h2>Inventory</h2>
      <UiDataTable>
        <thead>
          <tr>
            <th>
              <input
                class="selection-checkbox"
                type="checkbox"
                :checked="allSelected"
                :disabled="appState.repeaters.length === 0"
                @change="toggleSelectAll"
              />
            </th>
            <th>Node</th>
            <th>Status</th>
            <th>Location</th>
            <th>Firmware</th>
            <th>Last inform</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="repeater in appState.repeaters"
            :key="repeater.id"
            class="row-click"
            :class="{ selected: isSelected(repeater.id) }"
            @click="toggleRowSelection(repeater.id)"
          >
            <td>
              <input
                class="selection-checkbox"
                type="checkbox"
                :checked="isSelected(repeater.id)"
                @click.stop
                @change="toggleRowSelection(repeater.id)"
              />
            </td>
            <td>
              <strong>{{ repeater.node_name }}</strong>
              <p class="section-subtitle">{{ repeater.pubkey }}</p>
              <span v-if="isRepeaterStale(repeater.last_inform_at)" class="pill pill-red">stale</span>
              <span v-if="hasInformWarning(repeater.last_inform_at)" class="pill pill-red">no inform >10m</span>
              <span
                v-if="isConnectedButSilent(repeater.status, repeater.last_inform_at)"
                class="pill pill-yellow"
              >
                possible cert/tls issue
              </span>
            </td>
            <td><StatusPill :status="repeater.status" /></td>
            <td>{{ repeater.location || "—" }}</td>
            <td>{{ repeater.firmware_version || "—" }}</td>
            <td>{{ formatTimestamp(repeater.last_inform_at) }}</td>
            <td>
              <div class="row-actions">
                <router-link :to="`/repeaters/${repeater.id}`" class="btn btn-secondary btn-sm" @click.stop>
                  View
                </router-link>
                <button
                  class="btn btn-danger btn-sm"
                  :disabled="!canOperate || appState.actionLoading"
                  @click.stop="removeOne(repeater.id, repeater.node_name)"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="appState.repeaters.length === 0">
            <td colspan="7" class="section-subtitle">No repeaters found.</td>
          </tr>
        </tbody>
      </UiDataTable>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";

import StatusPill from "../components/ui/StatusPill.vue";
import { COMMAND_ACTIONS, type CommandAction } from "../types";
import {
  appState,
  canOperate,
  formatTimestamp,
  queueBulkCommands,
  refreshAllData,
  removeRepeaterRecord,
  removeStaleRepeaterRecords,
} from "../state/appState";

const staleHours = ref(168);
const selectedIds = ref<string[]>([]);

const bulkForm = reactive({
  action: "restart_service" as CommandAction,
  reason: "",
  paramsJson: "{}",
});

const selectedCount = computed(() => selectedIds.value.length);
const allSelected = computed(
  () => appState.repeaters.length > 0 && selectedIds.value.length === appState.repeaters.length,
);

const staleCount = computed(() =>
  appState.repeaters.filter((repeater) => isRepeaterStale(repeater.last_inform_at)).length,
);

function isSelected(repeaterId: string): boolean {
  return selectedIds.value.includes(repeaterId);
}

function toggleRowSelection(repeaterId: string): void {
  if (isSelected(repeaterId)) {
    selectedIds.value = selectedIds.value.filter((id) => id !== repeaterId);
    return;
  }
  selectedIds.value = [...selectedIds.value, repeaterId];
}

function toggleSelectAll(): void {
  if (allSelected.value) {
    clearSelection();
    return;
  }
  selectedIds.value = appState.repeaters.map((repeater) => repeater.id);
}

function clearSelection(): void {
  selectedIds.value = [];
}

function isRepeaterStale(lastInformAt: string | null): boolean {
  if (!lastInformAt) {
    return true;
  }
  const timestamp = new Date(lastInformAt).getTime();
  if (Number.isNaN(timestamp)) {
    return true;
  }
  return Date.now() - timestamp > staleHours.value * 60 * 60 * 1000;
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

function isConnectedButSilent(status: string, lastInformAt: string | null): boolean {
  return status === "connected" && hasInformWarning(lastInformAt);
}

async function queueBulkAction(): Promise<void> {
  if (selectedIds.value.length === 0) {
    appState.toastError = "Select at least one repeater first.";
    return;
  }
  let params: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(bulkForm.paramsJson.trim() || "{}");
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("Params JSON must be an object.");
    }
    params = parsed as Record<string, unknown>;
  } catch (error) {
    appState.toastError = error instanceof Error ? error.message : "Invalid Params JSON.";
    return;
  }

  const selectedRepeaters = appState.repeaters.filter((repeater) =>
    selectedIds.value.includes(repeater.id),
  );
  const queued = await queueBulkCommands(
    selectedRepeaters.map((repeater) => ({
      node_name: repeater.node_name,
      action: bulkForm.action,
      params,
      requested_by: appState.user?.email || "operator",
      reason: bulkForm.reason || undefined,
    })),
  );
  if (queued > 0) {
    clearSelection();
  }
}

async function removeOne(repeaterId: string, nodeName: string): Promise<void> {
  if (!window.confirm(`Delete repeater ${nodeName}?`)) {
    return;
  }
  await removeRepeaterRecord(repeaterId);
  selectedIds.value = selectedIds.value.filter((id) => id !== repeaterId);
}

async function removeStale(): Promise<void> {
  if (!window.confirm(`Remove repeaters with no inform for at least ${staleHours.value} hours?`)) {
    return;
  }
  const removed = await removeStaleRepeaterRecords(staleHours.value);
  if (removed > 0) {
    const remainingIds = new Set(appState.repeaters.map((repeater) => repeater.id));
    selectedIds.value = selectedIds.value.filter((id) => remainingIds.has(id));
  }
}
</script>

<style scoped>
.inline-controls {
  display: flex;
  gap: 0.75rem;
  align-items: end;
}

.selection-checkbox {
  width: 1rem;
  height: 1rem;
}

.row-actions {
  display: flex;
  gap: 0.5rem;
}

@media (max-width: 740px) {
  .inline-controls {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
