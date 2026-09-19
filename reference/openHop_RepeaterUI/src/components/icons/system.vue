<script lang="ts">
export default {
  name: 'SystemIcon',
};
</script>

<template>
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <!-- Monitor/Screen -->
    <rect
      x="2"
      y="3"
      width="10"
      height="7"
      rx="0.5"
      fill="none"
      stroke="currentColor"
      stroke-width="1.2"
    />

    <!-- Chart bars on screen -->
    <rect x="4" y="7" width="1" height="2" fill="currentColor" />
    <rect x="6" y="6" width="1" height="3" fill="currentColor" />
    <rect x="8" y="5" width="1" height="4" fill="currentColor" />
    <rect x="10" y="6.5" width="1" height="2.5" fill="currentColor" />
  </svg>
</template>
