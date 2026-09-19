<template>
  <article class="glass-card stat-card">
    <h3>{{ title }}</h3>
    <strong>{{ value }}</strong>
    <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  value: string | number;
  subtitle?: string;
}>();
</script>
