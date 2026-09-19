import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import ApiService from '@/utils/api';
import type { NeighborScopeRecord } from '@/generated/openapi';
import { parseScopeNames } from '@/utils/neighborScopes';

export interface Advert {
  id: number;
  timestamp: number;
  pubkey: string;
  node_name: string | null;
  is_repeater: boolean;
  route_type: number | null;
  contact_type: string;
  latitude: number | null;
  longitude: number | null;
  first_seen: number;
  last_seen: number;
  rssi: number | null;
  snr: number | null;
  advert_count: number;
  is_new_neighbor: boolean;
  zero_hop: boolean;
}

export const CONTACT_TYPE_MAP = {
  0: 'Unknown',
  1: 'Chat Node',
  2: 'Repeater',
  3: 'Room Server',
  4: 'Hybrid Node',
} as const;

export type { NeighborScopeRecord };

export const useNeighborStore = defineStore('neighbors', () => {
  const advertsByType = ref<Record<string, Advert[]>>({});
  // Last known region scopes, keyed by lowercase pubkey hex. Only repeaters that
  // have been queried appear here; an absent key means "never asked", which the
  // table renders differently from a query that came back empty.
  const scopesByPubkey = ref<Record<string, NeighborScopeRecord>>({});
  // This repeater's own advertised scopes: the wildcard plus every allow-flood
  // region, as the repeater itself formats them.
  const servedScopes = ref<string[]>([]);
  const isLoading = ref(false);
  const lastFetched = ref<number | null>(null);
  const currentHours = ref(48);
  const pageSize = 500;
  const maxPagesPerType = 200;

  const allAdverts = computed(() => Object.values(advertsByType.value).flat());
  const totalCount = computed(() => allAdverts.value.length);

  function isStale(ttlMs = 10 * 60_000): boolean {
    if (lastFetched.value === null) return true;
    return Date.now() - lastFetched.value > ttlMs;
  }

  async function fetchAll(hours = currentHours.value): Promise<void> {
    isLoading.value = true;
    currentHours.value = hours;

    const entries = Object.entries(CONTACT_TYPE_MAP) as [string, string][];

    const results = await Promise.allSettled(
      entries.map(async ([typeKey, typeName]) => {
        try {
          const adverts: Advert[] = [];
          let offset = 0;
          let pageCount = 0;

          while (pageCount < maxPagesPerType) {
            const response = await ApiService.get(
              `/adverts_by_contact_type?contact_type=${encodeURIComponent(typeName)}&hours=${hours}&limit=${pageSize}&offset=${offset}`,
            );

            const page =
              response.success && Array.isArray(response.data) ? (response.data as Advert[]) : [];

            if (page.length === 0) {
              break;
            }

            adverts.push(...page);

            if (page.length < pageSize) {
              break;
            }

            offset += pageSize;
            pageCount += 1;
          }

          return {
            typeKey,
            adverts,
          };
        } catch {
          return { typeKey, adverts: [] as Advert[] };
        }
      }),
    );

    const next: Record<string, Advert[]> = {};
    for (const result of results) {
      if (result.status === 'fulfilled' && result.value.adverts.length > 0) {
        next[result.value.typeKey] = result.value.adverts;
      }
    }
    advertsByType.value = next;
    lastFetched.value = Date.now();
    isLoading.value = false;

    // Fetched alongside the adverts but never allowed to fail them: a repeater
    // that predates the scopes endpoint (or has never run a query) just leaves
    // the column empty.
    await fetchScopes();
  }

  /** Returns whether the read succeeded, so a caller can offer a retry. */
  async function fetchScopes(): Promise<boolean> {
    try {
      const response = await ApiService.getNeighborScopes();
      const ok = response.success === true;
      scopesByPubkey.value = ok && response.data ? response.data : {};
      // The repeater reports its own scopes with the same formatter it answers a
      // neighbour's query with, so "we serve this too" is judged against exactly
      // what we would tell them.
      servedScopes.value = ok ? parseScopeNames(response.served?.scopes) : [];
      return ok;
    } catch {
      scopesByPubkey.value = {};
      servedScopes.value = [];
      return false;
    }
  }

  /**
   * Every region any neighbour has reported, deduplicated case-insensitively.
   *
   * The wildcard is left out: it is not a region and has no transport key, so it
   * cannot be carried. Names come from each neighbour's last answer, which is
   * kept even when a later query failed, so a rate-limited neighbour still
   * contributes what it told us before.
   */
  const discoveredScopes = computed(() => {
    const byKey = new Map<string, { name: string; neighbors: string[] }>();
    for (const [pubkey, record] of Object.entries(scopesByPubkey.value)) {
      for (const name of parseScopeNames(record.scopes)) {
        if (name === '*') continue;
        const key = name.toLowerCase();
        const entry = byKey.get(key);
        if (entry) {
          if (!entry.neighbors.includes(pubkey)) entry.neighbors.push(pubkey);
        } else {
          byKey.set(key, { name, neighbors: [pubkey] });
        }
      }
    }
    return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name));
  });

  /** Whether this repeater already serves a scope, matched case-insensitively. */
  function servesScope(name: string): boolean {
    const wanted = name.trim().toLowerCase();
    return servedScopes.value.some((served) => served.toLowerCase() === wanted);
  }

  /** Merge one query's outcome in without re-reading the whole table. */
  function setScope(pubkey: string, record: NeighborScopeRecord): void {
    scopesByPubkey.value = { ...scopesByPubkey.value, [pubkey.toLowerCase()]: record };
  }

  function reset(): void {
    advertsByType.value = {};
    scopesByPubkey.value = {};
    servedScopes.value = [];
    isLoading.value = false;
    lastFetched.value = null;
    currentHours.value = 48;
  }

  return {
    advertsByType,
    scopesByPubkey,
    servedScopes,
    discoveredScopes,
    isLoading,
    lastFetched,
    currentHours,
    allAdverts,
    totalCount,
    isStale,
    fetchAll,
    fetchScopes,
    servesScope,
    setScope,
    reset,
  };
});
