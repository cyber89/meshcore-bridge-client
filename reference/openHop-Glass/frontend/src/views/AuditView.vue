<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Audit Trail</h1>
        <p class="section-subtitle">Browse operator and system events.</p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="loadAudit">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh" }}
      </button>
    </header>

    <section class="glass-card panel">
      <form class="filter-grid" @submit.prevent="loadAudit">
        <label class="field-label">
          Limit
          <input v-model.number="limit" class="field" min="1" max="1000" type="number" />
        </label>
        <label class="field-label">
          Search text
          <input
            v-model.trim="searchText"
            class="field"
            placeholder="action / target / id / details values"
          />
        </label>
        <button class="btn btn-secondary">Apply</button>
      </form>
    </section>

    <section class="glass-card panel">
      <UiDataTable>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Action</th>
            <th>User</th>
            <th>Target</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in filteredAudit" :key="entry.id">
            <td>{{ formatTimestamp(entry.timestamp) }}</td>
            <td>{{ entry.action }}</td>
            <td>{{ entry.user_id || "system" }}</td>
            <td>{{ entry.target_type || "—" }} · {{ entry.target_id || "—" }}</td>
            <td>
              <pre class="details-json">{{ compactJson(entry.details) }}</pre>
            </td>
          </tr>
          <tr v-if="filteredAudit.length === 0">
            <td colspan="5" class="section-subtitle">No matching audit entries.</td>
          </tr>
        </tbody>
      </UiDataTable>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";

import { appState, formatTimestamp, refreshAuditEntries } from "../state/appState";

const limit = ref(200);
const searchText = ref("");

const filteredAudit = computed(() => {
  const query = searchText.value.trim().toLowerCase();
  if (!query) {
    return appState.audits;
  }
  return appState.audits.filter((entry) => {
    const details = JSON.stringify(entry.details ?? {}).toLowerCase();
    return (
      entry.action.toLowerCase().includes(query) ||
      (entry.target_type || "").toLowerCase().includes(query) ||
      (entry.target_id || "").toLowerCase().includes(query) ||
      (entry.user_id || "").toLowerCase().includes(query) ||
      details.includes(query)
    );
  });
});

async function loadAudit(): Promise<void> {
  try {
    await refreshAuditEntries(limit.value);
  } catch {
    // Error already surfaced via global toast.
  }
}

function compactJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}
</script>

<style scoped>

.filter-grid {
  display: grid;
  gap: 0.7rem;
  grid-template-columns: 180px 1fr auto;
  align-items: end;
}

.details-json {
  margin: 0;
  white-space: pre-wrap;
  font-size: 0.76rem;
  color: #d2deef;
}

@media (max-width: 740px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
