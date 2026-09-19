<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useDataService } from '@/stores/dataService';
import { useWebSocketStore } from '@/stores/websocket';
import Spinner from '@/components/ui/Spinner.vue';

const dataService = useDataService();
const wsStore = useWebSocketStore();

type Phase = 'loading' | 'connecting' | 'connected' | 'closed';

// Initialise phase based on current store state at mount time.
// "not bootstrapping" is ambiguous — it's also true BEFORE bootstrap starts,
// so check loadProgress to distinguish "not started yet" from "already done".
function initialPhase(): Phase {
  if (wsStore.isConnected) return 'closed';
  const notStarted = Object.values(dataService.loadProgress).every((s) => s === 'pending');
  if (notStarted || dataService.isBootstrapping) return 'loading';
  return 'connecting';
}

const phase = ref<Phase>(initialPhase());
let closeTimer: number | null = null;

const show = computed(() => phase.value !== 'closed');
const hasErrors = computed(() => Object.values(dataService.loadProgress).some((s) => s === 'error'));
const completedSteps = computed(() =>
  Object.values(dataService.loadProgress).filter((s) => s === 'done' || s === 'error').length,
);
const totalSteps = computed(() => Object.keys(dataService.loadProgress).length);
const statusTitle = computed(() => {
  if (phase.value === 'connected') return hasErrors.value ? 'Started with issues' : 'Ready';
  if (phase.value === 'connecting') return 'Loading data...';
  return 'Starting up...';
});
const statusDetail = computed(() => {
  if (phase.value === 'connected') {
    return hasErrors.value
      ? 'Some startup requests failed. You can keep using the dashboard.'
      : 'Realtime connection established.';
  }

  if (phase.value === 'connecting') {
    return 'Opening realtime connection...';
  }

  const progress = `${completedSteps.value}/${totalSteps.value}`;
  return `Loading data ${progress}`;
});

// Move to 'connecting' when DataService bootstrap finishes.
// If WS already opened during bootstrap, skip straight to 'connected'.
watch(
  () => dataService.isBootstrapping,
  (loading) => {
    if (!loading && phase.value === 'loading') {
      if (wsStore.isConnected) {
        phase.value = 'connected';
        closeTimer = window.setTimeout(() => {
          phase.value = 'closed';
        }, 2200);
      } else {
        phase.value = 'connecting';
      }
    }
  },
);

// Move to 'connected' when WS opens — only once bootstrap is done (phase === 'connecting').
// If WS opens while still bootstrapping, the bootstrap watcher above handles it.
watch(
  () => wsStore.connectionState,
  (state) => {
    if (state === 'open' && phase.value === 'connecting') {
      phase.value = 'connected';
      closeTimer = window.setTimeout(() => {
        phase.value = 'closed';
      }, 2200);
    }
  },
);

onUnmounted(() => {
  if (closeTimer !== null) clearTimeout(closeTimer);
});
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-250 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-500 ease-in"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="show"
        class="pointer-events-none fixed z-[500] right-2 bottom-[calc(var(--app-safe-area-bottom)+5.5rem)] sm:right-4 sm:bottom-[calc(var(--app-safe-area-bottom)+1rem)]"
      >
        <div
          class="pointer-events-auto w-[min(20rem,calc(100vw-1rem))] sm:w-[min(22rem,calc(100vw-1.5rem))] rounded-xl border shadow-lg backdrop-blur-sm px-3 py-2.5 sm:px-3.5 sm:py-3 transition-colors"
          :class="[
            phase === 'connected' && hasErrors
              ? 'bg-black/90 border-warning/50 text-white'
              : phase === 'connected'
                ? 'bg-black/90 border-accent-green/50 text-white'
                : 'bg-black/85 border-white/20 text-white',
          ]"
        >
          <div class="flex items-start gap-2.5">
            <div class="mt-0.5 flex-shrink-0">
              <Spinner
                v-if="phase === 'loading' || phase === 'connecting'"
                size="sm"
                color="current"
              />
              <svg
                v-else-if="phase === 'connected' && !hasErrors"
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
              <svg
                v-else
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v4m0 4h.01M4.93 19h14.14c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.2 16c-.77 1.33.19 3 1.73 3z" />
              </svg>
            </div>

            <div class="min-w-0">
              <p class="text-sm font-semibold leading-5">
                {{ statusTitle }}
              </p>
              <p
                class="mt-0.5 text-xs leading-4"
                :class="phase === 'connected' ? 'text-white/85' : 'text-white/80'"
              >
                {{ statusDetail }}
              </p>

              <p
                v-if="phase !== 'connected' && hasErrors"
                class="mt-1 text-[11px] leading-4 text-warning"
              >
                Some requests failed. Startup will continue.
              </p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
