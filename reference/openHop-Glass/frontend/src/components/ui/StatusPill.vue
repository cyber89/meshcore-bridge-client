<template>
  <span class="pill" :class="pillClass">{{ status }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status: string }>();

const pillClass = computed(() => {
  const status = props.status.toLowerCase();
  if (["connected", "success", "adopted", "resolved", "sent"].includes(status)) {
    return "pill-green";
  }
  if (["queued", "pending_adoption", "in_progress", "dispatched", "acknowledged"].includes(status)) {
    return "pill-amber";
  }
  if (["failed", "rejected", "offline", "active"].includes(status)) {
    return "pill-red";
  }
  return "pill-gray";
});
</script>
