<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Repeater Map</h1>
        <p class="section-subtitle">
          Location-based fleet visibility. Location format expected: <code>lat,lng</code>.
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshAllData()">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh map data" }}
      </button>
    </header>

    <section class="grid-3">
      <UiStatCard title="Total Repeaters" :value="appState.repeaters.length" />
      <UiStatCard title="Mapped (coords)" :value="mappedRepeaters.length" />
      <UiStatCard title="Missing Coordinates" :value="unmappedRepeaters.length" />
    </section>

    <article class="glass-card panel">
      <h2>Geospatial Plot</h2>
      <p v-if="mappedRepeaters.length === 0" class="section-subtitle">
        No parseable coordinates. Set repeater location as <code>lat,lng</code> (example: <code>51.5074,-0.1278</code>).
      </p>
      <svg v-else class="map-canvas" viewBox="0 0 1000 500" role="img" aria-label="Repeater map">
        <rect x="0" y="0" width="1000" height="500" rx="12" class="map-bg" />
        <g class="map-grid">
          <line v-for="line in 9" :key="`h-${line}`" :x1="0" :y1="line * 50" :x2="1000" :y2="line * 50" />
          <line v-for="line in 19" :key="`v-${line}`" :x1="line * 50" :y1="0" :x2="line * 50" :y2="500" />
        </g>
        <g>
          <circle
            v-for="item in mappedRepeaters"
            :key="item.id"
            :cx="item.x"
            :cy="item.y"
            r="7"
            :fill="statusColor(item.status)"
            stroke="#dce8ff"
            stroke-width="1.2"
          >
            <title>{{ `${item.node_name} (${item.location}) - ${item.status}` }}</title>
          </circle>
        </g>
      </svg>
    </article>

    <section class="grid-2">
      <article class="glass-card panel">
        <h2>Mapped Repeaters</h2>
        <UiDataTable>
          <thead>
            <tr>
              <th>Node</th>
              <th>Coordinates</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in mappedRepeaters" :key="item.id">
              <td>{{ item.node_name }}</td>
              <td><code>{{ item.location }}</code></td>
              <td><StatusPill :status="item.status" /></td>
            </tr>
            <tr v-if="mappedRepeaters.length === 0">
              <td colspan="3" class="section-subtitle">No mapped repeaters.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>

      <article class="glass-card panel">
        <h2>Repeaters Missing Coordinates</h2>
        <UiDataTable>
          <thead>
            <tr>
              <th>Node</th>
              <th>Location Field</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in unmappedRepeaters" :key="item.id">
              <td>{{ item.node_name }}</td>
              <td>{{ item.location || "—" }}</td>
              <td><StatusPill :status="item.status" /></td>
            </tr>
            <tr v-if="unmappedRepeaters.length === 0">
              <td colspan="3" class="section-subtitle">All repeaters include coordinates.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";

import StatusPill from "../components/ui/StatusPill.vue";
import { appState, refreshAllData } from "../state/appState";

interface MapPoint {
  id: string;
  node_name: string;
  location: string;
  status: string;
  x: number;
  y: number;
}

function parseCoords(location: string | null): { lat: number; lng: number } | null {
  if (!location) {
    return null;
  }

  const trimmed = location.trim();
  if (!trimmed) {
    return null;
  }

  try {
    if (trimmed.startsWith("{")) {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      return parseCoordsFromObject(parsed);
    }
  } catch {
    // Fall through to string parsing.
  }

  const directParts = trimmed
    .replace(";", ",")
    .split(",")
    .map((part) => Number.parseFloat(part.trim()))
    .filter((value) => !Number.isNaN(value));
  if (directParts.length >= 2) {
    return normalizeCoords(directParts[0], directParts[1]);
  }

  const numbers = trimmed.match(/[-+]?\d*\.?\d+/g);
  if (!numbers || numbers.length < 2) {
    return null;
  }
  const lat = Number.parseFloat(numbers[0]);
  const lng = Number.parseFloat(numbers[1]);
  return normalizeCoords(lat, lng);
}

function parseCoordsFromObject(value: Record<string, unknown>): { lat: number; lng: number } | null {
  const latRaw = value.lat ?? value.latitude;
  const lngRaw = value.lng ?? value.lon ?? value.longitude;
  const lat = Number.parseFloat(String(latRaw));
  const lng = Number.parseFloat(String(lngRaw));
  return normalizeCoords(lat, lng);
}

function normalizeCoords(lat: number, lng: number): { lat: number; lng: number } | null {
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    return null;
  }
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return null;
  }
  return { lat, lng };
}

const mappedRepeaters = computed<MapPoint[]>(() =>
  appState.repeaters
    .map((repeater) => {
      const coords = parseCoords(repeater.location);
      if (!coords || !repeater.location) {
        return null;
      }
      return {
        id: repeater.id,
        node_name: repeater.node_name,
        location: repeater.location,
        status: repeater.status,
        x: ((coords.lng + 180) / 360) * 1000,
        y: ((90 - coords.lat) / 180) * 500,
      };
    })
    .filter((value): value is MapPoint => Boolean(value)),
);

const unmappedRepeaters = computed(() =>
  appState.repeaters.filter((repeater) => parseCoords(repeater.location) === null),
);

onMounted(async () => {
  if (appState.token) {
    await refreshAllData();
  }
});

function statusColor(status: string): string {
  if (["adopted", "connected", "success"].includes(status)) {
    return "#56d88a";
  }
  if (["pending_adoption", "queued", "in_progress"].includes(status)) {
    return "#f5c159";
  }
  if (["failed", "rejected", "offline"].includes(status)) {
    return "#f08095";
  }
  return "#9fb2cf";
}
</script>

<style scoped>

.map-canvas {
  width: 100%;
  height: auto;
  min-height: 260px;
}

.map-bg {
  fill: #0a162a;
}

.map-grid line {
  stroke: rgba(152, 170, 200, 0.2);
  stroke-width: 1;
}
</style>
