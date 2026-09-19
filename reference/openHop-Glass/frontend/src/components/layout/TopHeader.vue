<template>
  <header class="glass-card flex flex-col items-stretch justify-between gap-3 px-4 py-3 lg:flex-row lg:items-center">
    <div class="flex items-center gap-3">
      <button class="btn btn-ghost inline-flex xl:hidden" @click="$emit('toggle-menu')">☰</button>
      <div>
        <h2 class="text-base font-semibold text-content-primary">Fleet Operations</h2>
        <p class="text-xs text-content-muted">
          {{ appState.user?.display_name || appState.user?.email }} · role:
          {{ appState.user?.role }}
        </p>
      </div>
    </div>
    <div class="flex flex-wrap items-center justify-end gap-2">
      <div class="hidden min-w-[220px] text-xs text-content-muted lg:grid">
        <span>API: {{ apiBaseLabel }}</span>
        <span>Last sync: {{ formatTimestamp(appState.lastSyncAt) }}</span>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshAllData()">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh" }}
      </button>
      <button class="btn btn-danger" @click="logoutAccount">Logout</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { getApiBaseUrl } from "../../api";
import { appState, formatTimestamp, logoutAccount, refreshAllData } from "../../state/appState";

const apiBaseLabel = getApiBaseUrl();

defineEmits<{ (e: "toggle-menu"): void }>();
</script>
