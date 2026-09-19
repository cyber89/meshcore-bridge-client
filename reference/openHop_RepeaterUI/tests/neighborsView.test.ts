import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';

const storage = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => void storage.set(key, String(value)),
  removeItem: (key: string) => void storage.delete(key),
  clear: () => storage.clear(),
  key: (index: number) => [...storage.keys()][index] ?? null,
  get length() {
    return storage.size;
  },
});

const neighborStore = {
  advertsByType: {},
  isLoading: false,
  currentHours: 48,
  scopesByPubkey: {},
  servedScopes: [],
  fetchAll: vi.fn(async () => {}),
  fetchScopes: vi.fn(async () => true),
  setScope: vi.fn(),
};

vi.mock('@/stores/system', () => ({
  useSystemStore: () => ({
    stats: { config: { repeater: { latitude: 1, longitude: 2 } } },
  }),
}));

vi.mock('@/stores/neighbors', () => ({
  useNeighborStore: () => neighborStore,
  CONTACT_TYPE_MAP: {
    0: 'Unknown',
    1: 'Chat Node',
    2: 'Repeater',
    3: 'Room Server',
    4: 'Hybrid Node',
  },
}));

vi.mock('@/stores/dataService', () => ({
  useDataService: () => ({ ensure: vi.fn() }),
}));

vi.mock('@/utils/api', () => ({
  default: {
    startNeighborDiscovery: vi.fn(),
    queryNeighborScopes: vi.fn(),
    createTransportKey: vi.fn(),
    deleteAdvert: vi.fn(),
    pingNeighbor: vi.fn(),
    addDiscoveredNeighbor: vi.fn(),
    getNeighborDiscoveryStreamUrl: vi.fn(),
  },
}));

vi.mock('@/components/modals/DeleteNeighborModal.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/modals/DiscoveryModal.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/ui/Spinner.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/modals/PingResultModal.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/modals/NeighborDetailsModal.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/modals/NeighborScopesModal.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/neighbors/NetworkMap.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));
vi.mock('@/components/neighbors/NeighborTable.vue', () => ({
  default: defineComponent({ template: '<div />' }),
}));

const { default: NeighborsView } = await import('@/views/Neighbors.vue');

describe('Neighbors view hours selection', () => {
  beforeEach(() => {
    storage.clear();
    neighborStore.advertsByType = {};
    neighborStore.isLoading = false;
    neighborStore.currentHours = 48;
    neighborStore.fetchAll.mockClear();
  });

  it('persists the selected hours value in local preferences', async () => {
    neighborStore.advertsByType = { '2': [] };
    const wrapper = mount(NeighborsView);
    const select = wrapper.findAll('select')[0];

    expect(select).toBeTruthy();
    await select.setValue('168');

    expect(storage.get('pymc_pref_neighbors_selectedHours')).toBe('168');
    expect(neighborStore.fetchAll).toHaveBeenCalledWith(168);
  });
});
