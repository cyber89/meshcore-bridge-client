<script setup lang="ts">
import PacketTable from '@/components/tables/PacketTable.vue';

defineOptions({ name: 'PacketArchiveView' });
</script>

<template>
  <div class="space-y-4">
    <PacketTable mode="archive" title="Packet Archive" :default-hours="24" />
  </div>
</template>
