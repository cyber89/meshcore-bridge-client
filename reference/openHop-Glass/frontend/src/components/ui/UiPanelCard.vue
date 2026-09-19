<template>
  <article class="glass-card panel">
    <header
      v-if="title || subtitle || $slots.header || $slots.actions"
      class="flex flex-wrap items-start justify-between gap-3"
    >
      <slot name="header">
        <div class="grid gap-1">
          <h2 v-if="title" class="text-base font-semibold text-content-primary">{{ title }}</h2>
          <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
        </div>
      </slot>
      <slot name="actions" />
    </header>
    <slot />
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  subtitle?: string;
}>();
</script>
