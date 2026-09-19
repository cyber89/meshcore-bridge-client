<script setup lang="ts">
import { computed } from 'vue';
import { Tag } from '@lucide/vue';
import Spinner from '@/components/ui/Spinner.vue';
import { formatPubkey, formatTimestamp, formatTimeAgo } from '@/utils/formatters';
import { describeScopes, UNSCOPED_WILDCARD } from '@/utils/neighborScopes';
import type { NeighborScopeRecord } from '@/generated/openapi';

defineOptions({ name: 'NeighborScopesModal' });

interface Neighbor {
  pubkey: string;
  node_name: string | null;
  zero_hop?: boolean;
}

interface Props {
  show: boolean;
  neighbor: Neighbor | null;
  /** Stored record for this neighbour, or null when it has never been queried. */
  record?: NeighborScopeRecord | null;
  /** This repeater's own advertised scopes, for the shared/not-shared split. */
  servedScopes?: string[];
  /** Scope name currently being added, so only its own button shows progress. */
  addingScope?: string | null;
  loading?: boolean;
  error?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  record: null,
  servedScopes: () => [],
  addingScope: null,
  loading: false,
  error: null,
});

const emit = defineEmits<{
  close: [];
  query: [neighbor: Neighbor];
  'add-scope': [scope: string];
}>();

const display = computed(() => describeScopes(props.record));

const servesScope = (name: string) =>
  props.servedScopes.some((served) => served.toLowerCase() === name.trim().toLowerCase());

const scopeBadges = computed(() =>
  display.value.names.map((name) => {
    const shared = servesScope(name);
    return {
      name,
      shared,
      // The wildcard is not a region and has no transport key -- it is this node's
      // own unscoped-flood switch -- so it is never offered as something to add.
      canAdd: !shared && name !== UNSCOPED_WILDCARD,
      busy: props.addingScope === name,
    };
  }),
);

const respondedAt = computed(() => {
  const at = props.record?.responded_at;
  return at ? { absolute: formatTimestamp(at), relative: formatTimeAgo(new Date(at * 1000)) } : null;
});

const queriedAt = computed(() => {
  const at = props.record?.queried_at;
  return at ? { absolute: formatTimestamp(at), relative: formatTimeAgo(new Date(at * 1000)) } : null;
});

// A route-direct request with an empty path reaches a zero-hop neighbour only, so
// a multi-hop repeater will time out however healthy it is. Say so up front rather
// than letting the operator read it as the neighbour being down.
const multiHopWarning = computed(
  () => props.neighbor !== null && props.neighbor.zero_hop === false,
);

const close = () => emit('close');

const runQuery = () => {
  if (props.loading || !props.neighbor) return;
  emit('query', props.neighbor);
};

const addScope = (name: string) => {
  if (props.addingScope) return;
  emit('add-scope', name);
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show && neighbor" class="modal-backdrop" @click.self="close">
        <div class="modal-card-glass max-w-md overflow-hidden" @click.stop>
          <!-- Header -->
          <div
            class="bg-gradient-to-r from-primary/20 to-accent-cyan/20 border-b border-stroke-subtle dark:border-stroke/opacity-light px-6 py-4"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="p-2 bg-accent-cyan/opacity-medium dark:bg-primary/opacity-medium rounded-lg">
                  <Tag class="w-5 h-5 text-accent-cyan dark:text-primary" :stroke-width="2" />
                </div>
                <div>
                  <h2 class="text-xl font-bold text-content-primary">Region Scopes</h2>
                  <p class="text-sm text-content-secondary dark:text-content-muted">
                    {{ neighbor.node_name || 'Unknown Node' }}
                    <span class="font-mono text-xs">({{ formatPubkey(neighbor.pubkey) }})</span>
                  </p>
                </div>
              </div>
              <button
                @click="close"
                class="p-2 hover:bg-stroke-subtle dark:hover:bg-white/opacity-light rounded-lg transition-colors text-content-secondary dark:text-content-muted hover:text-content-primary dark:hover:text-content-primary"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="p-6 space-y-4">
            <!-- Scopes -->
            <div>
              <div class="text-content-secondary dark:text-content-muted text-sm mb-2">
                Scopes served
              </div>

              <template v-if="display.state === 'scoped'">
                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="badge in scopeBadges"
                    :key="badge.name"
                    :class="[
                      'inline-flex items-center gap-1 pl-2 rounded-full text-xs border',
                      badge.canAdd ? 'pr-1' : 'pr-2',
                      badge.shared
                        ? 'bg-accent-green/opacity-medium border-accent-green/opacity-heavy text-accent-green'
                        : 'bg-primary/opacity-medium border-primary/opacity-heavy text-primary',
                    ]"
                    :title="
                      badge.shared
                        ? `This repeater also serves ${badge.name}`
                        : badge.canAdd
                          ? `Add ${badge.name} to this repeater`
                          : `This repeater does not flood unscoped traffic`
                    "
                  >
                    <span class="py-1">{{ badge.name }}</span>
                    <button
                      v-if="badge.canAdd"
                      type="button"
                      class="flex items-center justify-center w-5 h-5 rounded-full text-accent-green hover:bg-accent-green/opacity-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      :disabled="addingScope !== null"
                      :aria-label="`Add ${badge.name} to this repeater`"
                      @click="addScope(badge.name)"
                    >
                      <Spinner v-if="badge.busy" size="xs" color="current" />
                      <svg
                        v-else
                        class="w-3.5 h-3.5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="3"
                          d="M12 5v14M5 12h14"
                        />
                      </svg>
                    </button>
                  </span>
                </div>
                <p class="text-content-muted text-xs mt-2">
                  <span class="text-accent-green">Green</span> is a scope this repeater also
                  serves; press
                  <span class="text-accent-green font-medium">+</span> to start serving one it
                  does not.
                </p>
              </template>

              <div v-else-if="display.state === 'unscoped'" class="flex items-center gap-2">
                <span
                  class="inline-block px-2 py-1 rounded-full text-xs border bg-background-mute dark:bg-white/opacity-subtle border-stroke-subtle dark:border-stroke/opacity-medium text-content-secondary dark:text-content-muted font-mono"
                >
                  *
                </span>
                <span class="text-content-secondary dark:text-content-muted text-sm">
                  Unscoped traffic only
                </span>
              </div>

              <p v-else class="text-content-muted text-sm">
                {{
                  display.state === 'unknown'
                    ? 'This repeater has not been asked for its scopes yet.'
                    : display.summary + '. No scopes have ever been recorded for it.'
                }}
              </p>
            </div>

            <!-- Freshness -->
            <div
              v-if="respondedAt || queriedAt"
              class="text-xs text-content-muted space-y-1 border-t border-stroke-subtle dark:border-stroke/opacity-light pt-3"
            >
              <div v-if="respondedAt" class="flex items-center justify-between gap-3">
                <span>Answered</span>
                <span :title="respondedAt.absolute">{{ respondedAt.relative }}</span>
              </div>
              <div v-if="queriedAt" class="flex items-center justify-between gap-3">
                <span>Last query</span>
                <span :title="queriedAt.absolute">
                  {{ queriedAt.relative }}
                  <template v-if="record && record.status !== 'responded'">
                    — {{ record.status === 'timeout' ? 'no reply' : 'could not send' }}
                  </template>
                </span>
              </div>
            </div>

            <!-- Stale answer -->
            <div
              v-if="display.stale"
              class="flex items-start gap-3 bg-accent-amber/opacity-light border border-accent-amber/opacity-medium rounded-[12px] p-3"
            >
              <svg
                class="w-5 h-5 text-accent-amber flex-shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-1.964-1.333-2.732 0L3.268 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <p class="text-xs text-content-secondary dark:text-content-muted leading-relaxed">
                These scopes are from an earlier answer — the most recent query did not get a
                reply, so they may be out of date.
              </p>
            </div>

            <!-- Multi-hop caveat -->
            <div
              v-if="multiHopWarning"
              class="flex items-start gap-3 bg-accent-amber/opacity-light border border-accent-amber/opacity-medium rounded-[12px] p-3"
            >
              <svg
                class="w-5 h-5 text-accent-amber flex-shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-1.964-1.333-2.732 0L3.268 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <p class="text-xs text-content-secondary dark:text-content-muted leading-relaxed">
                This repeater was last heard multi-hop. The scope request is sent direct with no
                path, so it will only be answered by a neighbour in radio range.
              </p>
            </div>

            <!-- Query error -->
            <div
              v-if="error"
              class="bg-accent-red/opacity-light border border-accent-red/opacity-medium rounded-[12px] p-3"
            >
              <p class="text-accent-red text-sm">{{ error }}</p>
            </div>

            <!-- In-flight -->
            <div v-if="loading" class="flex items-center gap-3 text-sm">
              <Spinner size="sm" />
              <div>
                <p class="text-content-primary">Asking for scopes…</p>
                <p class="text-content-muted text-xs">
                  One direct request; the reply usually lands within a few seconds.
                </p>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="border-t border-stroke-subtle dark:border-stroke/opacity-light px-6 py-4">
            <div class="flex gap-3">
              <button type="button" class="modal-btn-cancel" @click="close">Close</button>
              <button
                type="button"
                class="modal-btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="loading"
                @click="runQuery"
              >
                {{ display.state === 'unknown' ? 'Query Scopes' : 'Query Again' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active > div,
.modal-leave-active > div {
  transition: transform 0.2s ease;
}

.modal-enter-from > div,
.modal-leave-to > div {
  transform: scale(0.95);
}
</style>
