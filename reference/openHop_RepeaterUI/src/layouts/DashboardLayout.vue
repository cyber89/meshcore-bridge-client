<script setup lang="ts">
import { ref } from 'vue';
import Sidebar from '@/components/nav/Sidebar.vue';
import TopBar from '@/components/nav/TopBar.vue';

defineOptions({ name: 'DashboardLayout' });

const showMobileSidebar = ref(false);

const toggleMobileSidebar = () => {
  showMobileSidebar.value = !showMobileSidebar.value;
};

const closeMobileSidebar = () => {
  showMobileSidebar.value = false;
};
</script>

<template>
  <div class="h-screen h-[100dvh] bg-background dark:bg-background overflow-hidden relative font-sans">
    <!-- Light mode background gradient ellipses with OpenHop blue/purple brand colors -->
    <div
      class="hidden lg:block dark:hidden absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-blue-200/30 to-blue-100/20 blur-[120px] opacity-70 -top-[79px] left-[575px] mix-blend-normal pointer-events-none"
    ></div>

    <div
      class="hidden lg:block dark:hidden absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-purple-200/25 to-purple-100/15 blur-[120px] opacity-60 -top-[94px] -left-[92px] mix-blend-normal pointer-events-none"
    ></div>

    <div
      class="hidden lg:block dark:hidden absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-indigo-200/25 to-blue-100/15 blur-[120px] opacity-65 top-[373px] left-[246px] mix-blend-normal pointer-events-none"
    ></div>

    <!-- Dark mode background gradient ellipses with OpenHop blue/purple brand colors -->
    <div
      class="hidden lg:dark:block absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-blue-400/15 to-blue-300/opacity-subtle blur-[120px] opacity-80 -top-[79px] left-[575px] mix-blend-screen pointer-events-none"
    ></div>

    <div
      class="hidden lg:dark:block absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-purple-400/15 to-purple-300/opacity-subtle blur-[120px] opacity-75 -top-[94px] -left-[92px] mix-blend-screen pointer-events-none"
    ></div>

    <div
      class="hidden lg:dark:block absolute rounded-full -rotate-[24.22deg] w-[705px] h-[512px] bg-gradient-to-b from-indigo-400/15 to-indigo-300/opacity-subtle blur-[120px] opacity-80 top-[373px] left-[246px] mix-blend-screen pointer-events-none"
    ></div>

    <div class="relative flex h-full">
      <Sidebar :mobile-open="showMobileSidebar" @close="closeMobileSidebar" />

      <!-- Main Content -->
      <main class="flex-1 p-4 pb-[calc(var(--app-safe-area-bottom)+1rem)] lg:p-[15px] lg:pb-[15px] overflow-y-auto overscroll-contain h-full [webkit-overflow-scrolling:touch]">
        <!-- Top Bar -->
        <TopBar @toggle-mobile-sidebar="toggleMobileSidebar" />

        <router-view />
      </main>
    </div>
  </div>
</template>
