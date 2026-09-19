<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Command Queue</h1>
        <p class="section-subtitle">Queue command jobs and inspect command execution detail.</p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="applyFilters">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh" }}
      </button>
    </header>

    <section class="grid-2">
      <article class="glass-card panel">
        <h2>Queue Command</h2>
        <p v-if="!canOperate" class="section-subtitle">Viewer accounts cannot queue commands.</p>
        <form class="panel-form" @submit.prevent="queueEntry">
          <label class="field-label">
            Node name
            <input v-model.trim="queueForm.node_name" class="field" required />
          </label>
          <label class="field-label">
            Action
            <select v-model="queueForm.action" class="field-select" required>
              <option v-for="action in COMMAND_ACTIONS" :key="action" :value="action">
                {{ action }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Reason
            <input v-model.trim="queueForm.reason" class="field" placeholder="Optional reason" />
          </label>
          <label class="field-label">
            Params JSON
            <textarea
              v-model="queueForm.paramsJson"
              class="field-textarea"
              placeholder='{"key":"value"}'
            />
          </label>
          <button class="btn btn-primary" :disabled="!canOperate || appState.actionLoading">
            {{ appState.actionLoading ? "Queueing..." : "Queue command" }}
          </button>
        </form>
      </article>

      <article class="glass-card panel">
        <h2>Filters</h2>
        <form class="panel-form" @submit.prevent="applyFilters">
          <label class="field-label">
            Status
            <input v-model.trim="filters.status" class="field" placeholder="queued / in_progress / success" />
          </label>
          <label class="field-label">
            Node name
            <input v-model.trim="filters.node_name" class="field" placeholder="node-01" />
          </label>
          <label class="field-label">
            Limit
            <input v-model.number="filters.limit" class="field" min="1" max="1000" type="number" />
          </label>
          <button class="btn btn-secondary" :disabled="appState.dataLoading">Apply filters</button>
        </form>
      </article>
    </section>

    <Teleport to="body">
      <div v-if="detailDialogOpen" class="detail-dialog-backdrop" @click.self="closeDetailDialog()">
        <section class="detail-dialog" role="dialog" aria-modal="true" aria-label="Command details">
          <header class="drawer-header">
            <div>
              <h2>Command Detail</h2>
              <p class="section-subtitle">{{ selectedCommandId ? selectedCommandId : "No selection" }}</p>
            </div>
            <button class="btn btn-ghost btn-sm" @click="closeDetailDialog()">Close</button>
          </header>
          <div class="drawer-body">
            <p v-if="detailLoading" class="section-subtitle">Loading command detail...</p>
            <p v-else-if="detailError" class="section-subtitle">{{ detailError }}</p>
            <div v-else-if="selectedCommandDetail">
              <p><strong>ID:</strong> <code>{{ selectedCommandDetail.command_id }}</code></p>
              <p><strong>Requested by:</strong> {{ selectedCommandDetail.requested_by || "—" }}</p>
              <p><strong>Completed:</strong> {{ formatTimestamp(selectedCommandDetail.completed_at) }}</p>
              <h3 class="detail-heading">Params</h3>
              <pre class="detail-json">{{ prettyJson(selectedCommandDetail.params) }}</pre>
              <h3 class="detail-heading">Result</h3>
              <pre class="detail-json">{{ prettyJson(selectedCommandDetail.result) }}</pre>
            </div>
            <p v-else class="section-subtitle">Select a command row to load detail.</p>
          </div>
        </section>
      </div>
    </Teleport>

    <section class="grid-1">
      <article class="glass-card panel">
        <h2>Queued Commands</h2>
        <UiDataTable>
          <thead>
            <tr>
              <th>Command</th>
              <th>Node</th>
              <th>Status</th>
              <th>Action</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="command in appState.commands"
              :key="command.command_id"
              class="row-click"
              :class="{ selected: selectedCommandId === command.command_id }"
              @click="inspectCommand(command.command_id)"
            >
              <td><code>{{ command.command_id }}</code></td>
              <td>{{ command.node_name }}</td>
              <td><StatusPill :status="command.status" /></td>
              <td>{{ command.action }}</td>
              <td>{{ formatTimestamp(command.created_at) }}</td>
            </tr>
            <tr v-if="appState.commands.length === 0">
              <td colspan="5" class="section-subtitle">No command entries found.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";

import StatusPill from "../components/ui/StatusPill.vue";
import { COMMAND_ACTIONS, type CommandQueueItemResponse } from "../types";
import {
  appState,
  canOperate,
  formatTimestamp,
  loadCommandDetail,
  queueCommandEntry,
  refreshCommandsList,
} from "../state/appState";

const queueForm = reactive({
  node_name: "",
  action: COMMAND_ACTIONS[0],
  paramsJson: "{}",
  reason: "",
});

const filters = reactive({
  status: "",
  node_name: "",
  limit: 200,
});

const selectedCommandId = ref<string | null>(null);
const selectedCommandDetail = ref<CommandQueueItemResponse | null>(null);
const detailDialogOpen = ref(false);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);

onMounted(() => {
  window.addEventListener("keydown", handleEscapeKey);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleEscapeKey);
});

async function queueEntry(): Promise<void> {
  try {
    let params: Record<string, unknown> = {};
    if (queueForm.paramsJson.trim()) {
      const parsed = JSON.parse(queueForm.paramsJson);
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        params = parsed as Record<string, unknown>;
      } else {
        throw new Error("Params JSON must be an object.");
      }
    }

    await queueCommandEntry({
      node_name: queueForm.node_name,
      action: queueForm.action,
      params,
      requested_by: appState.user?.email || "operator",
      reason: queueForm.reason || undefined,
    });

    queueForm.paramsJson = "{}";
    queueForm.reason = "";
  } catch (error) {
    appState.toastError = error instanceof Error ? error.message : "Invalid command payload.";
  }
}

async function applyFilters(): Promise<void> {
  try {
    await refreshCommandsList({
      status: filters.status || undefined,
      node_name: filters.node_name || undefined,
      limit: filters.limit,
    });
  } catch {
    // Error already surfaced via global toast.
  }
}

async function inspectCommand(commandId: string): Promise<void> {
  detailDialogOpen.value = true;
  detailLoading.value = true;
  detailError.value = null;
  selectedCommandDetail.value = null;
  try {
    selectedCommandId.value = commandId;
    selectedCommandDetail.value = await loadCommandDetail(commandId);
  } catch {
    detailError.value = "Failed to load command detail.";
    // Error already surfaced via global toast.
  } finally {
    detailLoading.value = false;
  }
}

function prettyJson(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  return JSON.stringify(value, null, 2);
}

function closeDetailDialog(): void {
  detailDialogOpen.value = false;
  detailLoading.value = false;
  detailError.value = null;
}

function handleEscapeKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && detailDialogOpen.value) {
    closeDetailDialog();
  }
}
</script>

<style scoped>
.detail-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2400;
  background: rgba(5, 10, 20, 0.58);
  display: grid;
  place-items: center;
  padding: 2.25rem;
}

.detail-dialog {
  width: min(760px, 92vw);
  max-height: min(80vh, 820px);
  background: rgba(6, 11, 20, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  backdrop-filter: blur(20px);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.85rem 0.95rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.drawer-body {
  padding: 0.85rem 0.95rem;
  display: grid;
  gap: 0.75rem;
  overflow-y: auto;
}

.detail-heading {
  margin-top: 0.8rem;
  margin-bottom: 0.35rem;
  font-size: 0.86rem;
}

.detail-json {
  margin: 0;
  padding: 0.72rem;
  border-radius: 10px;
  border: 1px solid var(--color-border-subtle);
  background: #081225;
  color: #dbe5f3;
  overflow-x: auto;
  font-size: 0.8rem;
}

@media (max-width: 900px) {
  .detail-dialog-backdrop {
    padding: 0.9rem;
  }

  .detail-dialog {
    width: 96vw;
    max-height: 86vh;
  }
}
</style>
