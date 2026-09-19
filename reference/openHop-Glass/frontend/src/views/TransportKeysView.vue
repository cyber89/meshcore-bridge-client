<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Transport Keys</h1>
        <p class="section-subtitle">
          Manage grouped transport keys and sync runtime key state to repeaters.
        </p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="loading" @click="loadTree()">
          {{ loading ? "Refreshing..." : "Refresh" }}
        </button>
        <button class="btn btn-ghost" :disabled="!canOperate || actionLoading" @click="syncNow()">
          Sync now
        </button>
        <button class="btn btn-primary" :disabled="!canOperate || actionLoading" @click="openCreateGroupModal()">
          New group
        </button>
        <button class="btn btn-primary" :disabled="!canOperate || actionLoading" @click="openCreateKeyModal()">
          New key
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="syncMessage" class="section-subtitle">{{ syncMessage }}</p>

    <section class="grid-3">
      <UiStatCard title="Total nodes" :value="nodes.length" subtitle="Groups + keys in tree" />
      <UiStatCard title="Groups" :value="groups.length" subtitle="Nested hierarchy nodes" />
      <UiStatCard title="Keys" :value="keys.length" subtitle="Leaf key records" />
    </section>

    <section class="grid-2 transport-main-grid">
      <UiPanelCard title="Transport Key Tree" subtitle="Click a row to inspect or edit.">
        <template #actions>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="!selectedNode || !canOperate || actionLoading"
            @click="openEditSelectedModal()"
          >
            Edit selected
          </button>
          <button
            class="btn btn-danger btn-sm"
            :disabled="!selectedNode || !canOperate || actionLoading"
            @click="openDeleteSelectedModal()"
          >
            Delete selected
          </button>
        </template>
        <UiDataTable>
          <thead>
            <tr>
              <th>Name</th>
              <th>Kind</th>
              <th>Flood</th>
              <th>Parent</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in flattenedRows"
              :key="row.node.id"
              class="row-click"
              :class="{ selected: selectedNodeId === row.node.id }"
              @click="selectedNodeId = row.node.id"
            >
              <td>
                <div class="tree-name" :style="{ paddingLeft: `${row.depth * 1.2}rem` }">
                  <span class="tree-glyph" :class="row.node.kind === 'group' ? 'group' : 'key'">
                    {{ row.node.kind === "group" ? "▸" : "•" }}
                  </span>
                  <span>{{ row.node.name }}</span>
                </div>
              </td>
              <td>
                <span class="pill" :class="row.node.kind === 'group' ? 'pill-amber' : 'pill-green'">
                  {{ row.node.kind }}
                </span>
              </td>
              <td>{{ row.node.flood_policy }}</td>
              <td>{{ parentName(row.node.parent_id) }}</td>
              <td>{{ formatTimestamp(row.node.updated_at) }}</td>
            </tr>
            <tr v-if="flattenedRows.length === 0">
              <td colspan="5" class="section-subtitle">
                No transport key nodes yet. Create a group or key to begin.
              </td>
            </tr>
          </tbody>
        </UiDataTable>
      </UiPanelCard>

      <UiPanelCard title="Selection Details" subtitle="Context and sync state for the active selection.">
        <div v-if="selectedNode" class="selection-grid">
          <div class="selection-row">
            <strong>Name</strong>
            <span>{{ selectedNode.name }}</span>
          </div>
          <div class="selection-row">
            <strong>Kind</strong>
            <span>{{ selectedNode.kind }}</span>
          </div>
          <div class="selection-row">
            <strong>Parent</strong>
            <span>{{ parentName(selectedNode.parent_id) }}</span>
          </div>
          <div class="selection-row">
            <strong>Flood policy</strong>
            <span>{{ selectedNode.flood_policy }}</span>
          </div>
          <div class="selection-row">
            <strong>Transport key</strong>
            <span class="mono-value">{{ selectedNode.transport_key || "Generated at apply-time" }}</span>
          </div>
          <div class="selection-row">
            <strong>Updated</strong>
            <span>{{ formatTimestamp(selectedNode.updated_at) }}</span>
          </div>
        </div>
        <p v-else class="section-subtitle">Select a node from the tree to inspect or edit it.</p>
      </UiPanelCard>
    </section>

    <UiPanelCard title="Repeater Sync Status" subtitle="Latest transport key sync state by repeater.">
      <UiDataTable>
        <thead>
          <tr>
            <th>Repeater</th>
            <th>Status</th>
            <th>Last update</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in pagedSyncRows" :key="row.repeater_id">
            <td>{{ row.node_name }}</td>
            <td><StatusPill :status="row.status" /></td>
            <td>{{ formatTimestamp(row.updated_at) }}</td>
            <td>{{ row.error_message || "—" }}</td>
          </tr>
          <tr v-if="pagedSyncRows.length === 0">
            <td colspan="4" class="section-subtitle">No repeaters found.</td>
          </tr>
        </tbody>
      </UiDataTable>
      <div class="pagination-row">
        <span class="section-subtitle">Page {{ syncPage }} / {{ syncPageCount }}</span>
        <div class="pagination-actions">
          <button class="btn btn-ghost btn-sm" :disabled="syncPage <= 1" @click="syncPage -= 1">
            Previous
          </button>
          <button class="btn btn-ghost btn-sm" :disabled="syncPage >= syncPageCount" @click="syncPage += 1">
            Next
          </button>
        </div>
      </div>
    </UiPanelCard>
  </section>

  <teleport to="body">
    <div v-if="showGroupModal" class="modal-backdrop" @click.self="closeGroupModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>{{ groupModalMode === "create" ? "Create Group" : "Edit Group" }}</h3>
            <p class="section-subtitle">Use nested groups to organize keys by region or domain.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeGroupModal()">Close</button>
        </header>
        <form class="panel-form" @submit.prevent="submitGroupModal()">
          <label class="field-label">
            Group name
            <input v-model.trim="groupForm.name" class="field" required />
          </label>
          <label class="field-label">
            Parent group
            <select v-model="groupForm.parent_group_id" class="field-select">
              <option value="">Root</option>
              <option v-for="group in groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Flood policy
            <select v-model="groupForm.flood_policy" class="field-select">
              <option value="allow">allow</option>
              <option value="deny">deny</option>
            </select>
          </label>
          <label class="field-label">
            Transport key (optional)
            <input
              v-model.trim="groupForm.transport_key"
              class="field"
              placeholder="Leave empty to auto-generate on repeater"
            />
          </label>
          <label class="field-label">
            Sort order
            <input v-model.number="groupForm.sort_order" type="number" min="0" class="field" />
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeGroupModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : groupModalMode === "create" ? "Create group" : "Save group" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showKeyModal" class="modal-backdrop" @click.self="closeKeyModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>{{ keyModalMode === "create" ? "Create Key" : "Edit Key" }}</h3>
            <p class="section-subtitle">Attach keys to groups and control flood policy per key.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeKeyModal()">Close</button>
        </header>
        <form class="panel-form" @submit.prevent="submitKeyModal()">
          <label class="field-label">
            Key name
            <input v-model.trim="keyForm.name" class="field" required />
          </label>
          <label class="field-label">
            Group
            <select v-model="keyForm.group_id" class="field-select">
              <option value="">Root</option>
              <option v-for="group in groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Flood policy
            <select v-model="keyForm.flood_policy" class="field-select">
              <option value="allow">allow</option>
              <option value="deny">deny</option>
            </select>
          </label>
          <label class="field-label">
            Transport key (optional)
            <input
              v-model.trim="keyForm.transport_key"
              class="field"
              placeholder="Leave empty to auto-generate on repeater"
            />
          </label>
          <label class="field-label">
            Sort order
            <input v-model.number="keyForm.sort_order" type="number" min="0" class="field" />
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeKeyModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : keyModalMode === "create" ? "Create key" : "Save key" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showDeleteGroupModal" class="modal-backdrop" @click.self="closeDeleteGroupModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Delete Group</h3>
            <p class="section-subtitle">
              Optionally reassign direct children before deleting this group.
            </p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeDeleteGroupModal()">Close</button>
        </header>
        <label class="field-label">
          Reassign direct children to
          <select v-model="deleteGroupReassignTargetId" class="field-select">
            <option value="">No reassign (delete subtree)</option>
            <option v-for="group in reassignableGroups" :key="group.id" :value="group.id">
              {{ group.name }}
            </option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="btn btn-ghost" type="button" @click="closeDeleteGroupModal()">Cancel</button>
          <button class="btn btn-danger" :disabled="!canOperate || actionLoading" @click="confirmDeleteGroup()">
            {{ actionLoading ? "Deleting..." : "Delete group" }}
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showDeleteKeyModal" class="modal-backdrop" @click.self="closeDeleteKeyModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Delete Key</h3>
            <p class="section-subtitle">This action cannot be undone.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeDeleteKeyModal()">Close</button>
        </header>
        <div class="modal-actions">
          <button class="btn btn-ghost" type="button" @click="closeDeleteKeyModal()">Cancel</button>
          <button class="btn btn-danger" :disabled="!canOperate || actionLoading" @click="confirmDeleteKey()">
            {{ actionLoading ? "Deleting..." : "Delete key" }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  createTransportKey,
  createTransportKeyGroup,
  deleteTransportKey,
  deleteTransportKeyGroup,
  getTransportKeyTree,
  triggerTransportKeySync,
  updateTransportKey,
  updateTransportKeyGroup,
} from "../api";
import StatusPill from "../components/ui/StatusPill.vue";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import { appState, canOperate, formatTimestamp } from "../state/appState";
import type {
  TransportKeySyncStatusResponse,
  TransportKeyTreeNodeResponse,
  TransportKeyTreeResponse,
} from "../types";

const loading = ref(false);
const actionLoading = ref(false);
const error = ref<string | null>(null);
const syncMessage = ref<string | null>(null);
const selectedNodeId = ref<string | null>(null);

const nodes = ref<TransportKeyTreeNodeResponse[]>([]);
const syncStatus = ref<TransportKeySyncStatusResponse[]>([]);

const showGroupModal = ref(false);
const groupModalMode = ref<"create" | "edit">("create");
const groupEditId = ref<string | null>(null);

const showKeyModal = ref(false);
const keyModalMode = ref<"create" | "edit">("create");
const keyEditId = ref<string | null>(null);

const showDeleteGroupModal = ref(false);
const showDeleteKeyModal = ref(false);
const deleteGroupReassignTargetId = ref("");

const syncPage = ref(1);
const syncPageSize = 10;

const groupForm = reactive({
  name: "",
  parent_group_id: "",
  flood_policy: "allow" as "allow" | "deny",
  transport_key: "",
  sort_order: 100,
});

const keyForm = reactive({
  name: "",
  group_id: "",
  flood_policy: "allow" as "allow" | "deny",
  transport_key: "",
  sort_order: 100,
});

const groups = computed(() => nodes.value.filter((node) => node.kind === "group"));
const keys = computed(() => nodes.value.filter((node) => node.kind === "key"));
const nodeById = computed(() => new Map(nodes.value.map((node) => [node.id, node])));
const selectedNode = computed(() =>
  selectedNodeId.value ? nodeById.value.get(selectedNodeId.value) ?? null : null,
);

const rootRows = computed(() =>
  nodes.value
    .filter((node) => !node.parent_id)
    .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)),
);

const childRowsByParent = computed(() => {
  const map = new Map<string, TransportKeyTreeNodeResponse[]>();
  for (const node of nodes.value) {
    if (!node.parent_id) {
      continue;
    }
    const list = map.get(node.parent_id) ?? [];
    list.push(node);
    map.set(node.parent_id, list);
  }
  for (const [parentId, list] of map.entries()) {
    map.set(
      parentId,
      [...list].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)),
    );
  }
  return map;
});

const flattenedRows = computed(() => {
  const rows: Array<{ node: TransportKeyTreeNodeResponse; depth: number }> = [];
  const visit = (node: TransportKeyTreeNodeResponse, depth: number): void => {
    rows.push({ node, depth });
    const children = childRowsByParent.value.get(node.id) ?? [];
    for (const child of children) {
      visit(child, depth + 1);
    }
  };
  for (const node of rootRows.value) {
    visit(node, 0);
  }
  return rows;
});

const syncPageCount = computed(() => Math.max(1, Math.ceil(syncStatus.value.length / syncPageSize)));
const pagedSyncRows = computed(() => {
  const start = (syncPage.value - 1) * syncPageSize;
  return syncStatus.value.slice(start, start + syncPageSize);
});

const reassignableGroups = computed(() => {
  const selectedId = selectedNode.value?.id;
  if (!selectedId) {
    return groups.value;
  }
  return groups.value.filter((group) => group.id !== selectedId);
});

onMounted(async () => {
  await loadTree();
});

function parentName(parentId: string | null): string {
  if (!parentId) {
    return "Root";
  }
  return nodeById.value.get(parentId)?.name ?? parentId;
}

function resetGroupForm(): void {
  groupForm.name = "";
  groupForm.parent_group_id = "";
  groupForm.flood_policy = "allow";
  groupForm.transport_key = "";
  groupForm.sort_order = 100;
}

function resetKeyForm(): void {
  keyForm.name = "";
  keyForm.group_id = "";
  keyForm.flood_policy = "allow";
  keyForm.transport_key = "";
  keyForm.sort_order = 100;
}

async function loadTree(): Promise<void> {
  if (!appState.token) {
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const payload: TransportKeyTreeResponse = await getTransportKeyTree(appState.token);
    nodes.value = payload.nodes;
    syncStatus.value = payload.sync_status;
    syncPage.value = Math.min(syncPage.value, syncPageCount.value);
    if (selectedNodeId.value && !nodeById.value.has(selectedNodeId.value)) {
      selectedNodeId.value = null;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed loading transport keys";
  } finally {
    loading.value = false;
  }
}

async function syncNow(): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  error.value = null;
  syncMessage.value = null;
  try {
    const result = await triggerTransportKeySync(appState.token);
    syncMessage.value = `Queued ${result.queued_commands} repeater sync command${result.queued_commands === 1 ? "" : "s"} (skipped ${result.skipped_commands}).`;
    await loadTree();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed queuing sync";
  } finally {
    actionLoading.value = false;
  }
}

function openCreateGroupModal(): void {
  resetGroupForm();
  if (selectedNode.value?.kind === "group") {
    groupForm.parent_group_id = selectedNode.value.id;
  }
  groupModalMode.value = "create";
  groupEditId.value = null;
  showGroupModal.value = true;
}

function openCreateKeyModal(): void {
  resetKeyForm();
  if (selectedNode.value?.kind === "group") {
    keyForm.group_id = selectedNode.value.id;
  }
  keyModalMode.value = "create";
  keyEditId.value = null;
  showKeyModal.value = true;
}

function openEditSelectedModal(): void {
  if (!selectedNode.value) {
    return;
  }
  if (selectedNode.value.kind === "group") {
    groupModalMode.value = "edit";
    groupEditId.value = selectedNode.value.id;
    groupForm.name = selectedNode.value.name;
    groupForm.parent_group_id = selectedNode.value.parent_id ?? "";
    groupForm.flood_policy = selectedNode.value.flood_policy === "deny" ? "deny" : "allow";
    groupForm.transport_key = selectedNode.value.transport_key ?? "";
    groupForm.sort_order = selectedNode.value.sort_order;
    showGroupModal.value = true;
    return;
  }
  keyModalMode.value = "edit";
  keyEditId.value = selectedNode.value.id;
  keyForm.name = selectedNode.value.name;
  keyForm.group_id = selectedNode.value.parent_id ?? "";
  keyForm.flood_policy = selectedNode.value.flood_policy === "deny" ? "deny" : "allow";
  keyForm.transport_key = selectedNode.value.transport_key ?? "";
  keyForm.sort_order = selectedNode.value.sort_order;
  showKeyModal.value = true;
}

function openDeleteSelectedModal(): void {
  if (!selectedNode.value) {
    return;
  }
  if (selectedNode.value.kind === "group") {
    deleteGroupReassignTargetId.value = "";
    showDeleteGroupModal.value = true;
    return;
  }
  showDeleteKeyModal.value = true;
}

function closeGroupModal(): void {
  showGroupModal.value = false;
  groupEditId.value = null;
}

function closeKeyModal(): void {
  showKeyModal.value = false;
  keyEditId.value = null;
}

function closeDeleteGroupModal(): void {
  showDeleteGroupModal.value = false;
  deleteGroupReassignTargetId.value = "";
}

function closeDeleteKeyModal(): void {
  showDeleteKeyModal.value = false;
}

async function submitGroupModal(): Promise<void> {
  if (!appState.token || !groupForm.name.trim()) {
    return;
  }
  actionLoading.value = true;
  error.value = null;
  syncMessage.value = null;
  try {
    if (groupModalMode.value === "create") {
      await createTransportKeyGroup(appState.token, {
        name: groupForm.name.trim(),
        parent_group_id: groupForm.parent_group_id || null,
        flood_policy: groupForm.flood_policy,
        transport_key: groupForm.transport_key.trim() || null,
        sort_order: groupForm.sort_order,
      });
    } else if (groupEditId.value) {
      await updateTransportKeyGroup(appState.token, groupEditId.value, {
        name: groupForm.name.trim(),
        parent_group_id: groupForm.parent_group_id || null,
        flood_policy: groupForm.flood_policy,
        transport_key: groupForm.transport_key.trim() || null,
        sort_order: groupForm.sort_order,
      });
    }
    closeGroupModal();
    await loadTree();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed saving group";
  } finally {
    actionLoading.value = false;
  }
}

async function submitKeyModal(): Promise<void> {
  if (!appState.token || !keyForm.name.trim()) {
    return;
  }
  actionLoading.value = true;
  error.value = null;
  syncMessage.value = null;
  try {
    if (keyModalMode.value === "create") {
      await createTransportKey(appState.token, {
        name: keyForm.name.trim(),
        group_id: keyForm.group_id || null,
        flood_policy: keyForm.flood_policy,
        transport_key: keyForm.transport_key.trim() || null,
        sort_order: keyForm.sort_order,
      });
    } else if (keyEditId.value) {
      await updateTransportKey(appState.token, keyEditId.value, {
        name: keyForm.name.trim(),
        group_id: keyForm.group_id || null,
        flood_policy: keyForm.flood_policy,
        transport_key: keyForm.transport_key.trim() || null,
        sort_order: keyForm.sort_order,
      });
    }
    closeKeyModal();
    await loadTree();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed saving key";
  } finally {
    actionLoading.value = false;
  }
}

async function confirmDeleteGroup(): Promise<void> {
  if (!appState.token || !selectedNode.value || selectedNode.value.kind !== "group") {
    return;
  }
  actionLoading.value = true;
  error.value = null;
  syncMessage.value = null;
  try {
    await deleteTransportKeyGroup(
      appState.token,
      selectedNode.value.id,
      deleteGroupReassignTargetId.value || null,
    );
    selectedNodeId.value = null;
    closeDeleteGroupModal();
    await loadTree();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed deleting group";
  } finally {
    actionLoading.value = false;
  }
}

async function confirmDeleteKey(): Promise<void> {
  if (!appState.token || !selectedNode.value || selectedNode.value.kind !== "key") {
    return;
  }
  actionLoading.value = true;
  error.value = null;
  syncMessage.value = null;
  try {
    await deleteTransportKey(appState.token, selectedNode.value.id);
    selectedNodeId.value = null;
    closeDeleteKeyModal();
    await loadTree();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed deleting key";
  } finally {
    actionLoading.value = false;
  }
}
</script>

<style scoped>
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.transport-main-grid {
  align-items: start;
}

.tree-name {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.tree-glyph {
  width: 1rem;
  text-align: center;
  opacity: 0.85;
}

.tree-glyph.group {
  color: #f5c568;
}

.tree-glyph.key {
  color: #88e4ac;
}

.selection-grid {
  display: grid;
  gap: 0.55rem;
}

.selection-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 0.6rem;
  align-items: start;
  color: var(--color-text-secondary);
}

.mono-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-top: 0.65rem;
}

.pagination-actions {
  display: inline-flex;
  gap: 0.45rem;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(3, 8, 16, 0.68);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.modal-card {
  width: min(560px, 100%);
  display: grid;
  gap: 0.85rem;
  padding: 1rem;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.error-text {
  color: #f8a8b8;
}
</style>
