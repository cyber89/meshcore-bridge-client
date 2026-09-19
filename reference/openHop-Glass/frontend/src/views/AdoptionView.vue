<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Adoption Queue</h1>
        <p class="section-subtitle">Approve or reject repeaters awaiting adoption.</p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshAllData()">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh" }}
      </button>
    </header>

    <article class="glass-card panel">
      <p v-if="!canOperate" class="section-subtitle">Viewer accounts cannot approve/reject adoption.</p>
      <UiDataTable>
        <thead>
          <tr>
            <th>Node</th>
            <th>Status</th>
            <th>Last inform</th>
            <th>Operator note</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="repeater in appState.pendingRepeaters" :key="repeater.id">
            <td>
              <strong>{{ repeater.node_name }}</strong>
              <p class="section-subtitle">{{ repeater.pubkey }}</p>
            </td>
            <td><StatusPill :status="repeater.status" /></td>
            <td>{{ formatTimestamp(repeater.last_inform_at) }}</td>
            <td>
              <input v-model.trim="notes[repeater.id]" class="field" placeholder="Optional note" />
            </td>
            <td>
              <div class="action-row">
                <button
                  class="btn btn-primary"
                  :disabled="!canOperate || appState.actionLoading"
                  @click="approve(repeater.id)"
                >
                  Adopt
                </button>
                <button
                  class="btn btn-danger"
                  :disabled="!canOperate || appState.actionLoading"
                  @click="reject(repeater.id)"
                >
                  Reject
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="appState.pendingRepeaters.length === 0">
            <td colspan="5" class="section-subtitle">No pending repeaters.</td>
          </tr>
        </tbody>
      </UiDataTable>
    </article>
  </section>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";

import StatusPill from "../components/ui/StatusPill.vue";
import {
  adoptPendingRepeater,
  appState,
  canOperate,
  formatTimestamp,
  refreshAllData,
  rejectPendingRepeater,
} from "../state/appState";

const notes = reactive<Record<string, string>>({});

async function approve(repeaterId: string): Promise<void> {
  try {
    await adoptPendingRepeater(repeaterId, notes[repeaterId]);
    notes[repeaterId] = "";
  } catch {
    // Error already surfaced via global toast.
  }
}

async function reject(repeaterId: string): Promise<void> {
  try {
    await rejectPendingRepeater(repeaterId, notes[repeaterId]);
    notes[repeaterId] = "";
  } catch {
    // Error already surfaced via global toast.
  }
}
</script>

<style scoped>

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
