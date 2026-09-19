<template>
  <div class="relative min-h-screen p-2 sm:p-4">
    <div
      class="pointer-events-none absolute -left-20 -top-20 h-[360px] w-[360px] rounded-full bg-cyan-400/15 blur-[120px]"
    />
    <div
      class="pointer-events-none absolute -right-20 top-8 h-[340px] w-[340px] rounded-full bg-violet-500/15 blur-[120px]"
    />
    <div
      class="pointer-events-none absolute bottom-[-80px] left-1/3 h-[360px] w-[360px] rounded-full bg-emerald-400/10 blur-[120px]"
    />

    <div class="relative grid gap-4 xl:grid-cols-[auto_minmax(0,1fr)]">
      <aside class="glass-card hidden min-h-[calc(100vh-2rem)] overflow-hidden xl:block">
        <SidebarNav />
      </aside>

      <div
        v-if="mobileMenuOpen"
        class="fixed inset-0 z-[1000] bg-slate-950/75 p-2 backdrop-blur-sm xl:hidden"
        @click="mobileMenuOpen = false"
      >
        <aside class="glass-card h-[calc(100vh-1rem)] w-[min(92vw,320px)] overflow-hidden" @click.stop>
          <SidebarNav mobile @navigate="mobileMenuOpen = false" />
        </aside>
      </div>

      <main class="grid min-h-[calc(100vh-1rem)] grid-rows-[auto_minmax(0,1fr)] gap-4">
        <TopHeader @toggle-menu="mobileMenuOpen = !mobileMenuOpen" />
        <section class="glass-card min-h-[calc(100vh-7rem)] p-4 sm:p-5">
          <router-view />
        </section>
      </main>
    </div>

    <p v-if="appState.toastSuccess" class="toast toast-success">{{ appState.toastSuccess }}</p>
    <p v-if="appState.toastError" class="toast toast-error">{{ appState.toastError }}</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import { appState, refreshAllData } from "../../state/appState";
import SidebarNav from "./SidebarNav.vue";
import TopHeader from "./TopHeader.vue";

const mobileMenuOpen = ref(false);

onMounted(async () => {
  if (appState.token) {
    await refreshAllData();
  }
});
</script>
