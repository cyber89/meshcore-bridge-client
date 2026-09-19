import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import RadioHardwareSettings from '@/components/configuration/RadioHardwareSettings.vue';
import { useSetupStore } from '@/stores/setup';
import { useSystemStore } from '@/stores/system';
import ApiService from '@/utils/api';

const apiMock = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getSerialPorts: vi.fn().mockResolvedValue({ success: true, data: [] }),
  importConfig: vi.fn().mockResolvedValue({ success: true, data: {} }),
}));

vi.mock('@/utils/api', () => ({
  default: apiMock,
  ApiService: apiMock,
  API_SERVER_URL: '',
  apiClient: {},
}));

vi.mock('@/composables/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    showUnsavedModal: false,
    requestLeave: vi.fn().mockResolvedValue(true),
    handleDiscard: vi.fn(),
    handleSave: vi.fn(),
    handleCancel: vi.fn(),
  }),
}));

function mountComponent(config: Record<string, unknown>) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const systemStore = useSystemStore();
  systemStore.stats = { config } as never;
  vi.spyOn(systemStore, 'fetchStats').mockResolvedValue({ config } as never);
  const setupStore = useSetupStore();
  vi.spyOn(setupStore, 'fetchRadioPresets').mockResolvedValue(undefined);
  return mount(RadioHardwareSettings, {
    global: {
      plugins: [pinia],
      stubs: { RestartModal: true, UnsavedChangesModal: true },
    },
  });
}

function buttonWithText(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text));
}

describe('RadioHardwareSettings modem transport naming', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('hydrates legacy TCP data into canonical UI state, prefers canonical fields, and hides backend tokens', async () => {
    const wrapper = mountComponent({
      radio_type: 'pymc_tcp',
      pymc_tcp: { host: 'legacy.local', port: 5055, token: 'legacy-secret' },
      modem_tcp: { host: 'canonical.local', port: 6000, token: 'canonical-secret' },
    });
    await flushPromises();

    expect(wrapper.text()).toContain('openHop Modem');
    expect(wrapper.text()).toContain('canonical.local');
    expect(wrapper.text()).toContain('6000');
    expect(wrapper.text()).not.toContain('legacy.local');
    expect(wrapper.text()).not.toContain('legacy-secret');
    expect(wrapper.text()).not.toContain('canonical-secret');
    expect(wrapper.text()).not.toContain('pymc_tcp firmware modem');
  });

  it('saves only canonical names and omits an untouched token', async () => {
    const wrapper = mountComponent({
      radio_type: 'pymc_tcp',
      pymc_tcp: { host: 'legacy.local', port: 5055, token: '[REDACTED]' },
    });
    await flushPromises();

    await buttonWithText(wrapper, 'Edit Settings')!.trigger('click');
    await buttonWithText(wrapper, 'Save Changes')!.trigger('click');
    await flushPromises();

    expect(ApiService.importConfig).toHaveBeenCalledWith({
      radio_type: 'modem_tcp',
      modem_tcp: { host: 'legacy.local', port: 5055 },
    });
  });

  it('submits a newly entered token under the canonical section', async () => {
    const wrapper = mountComponent({
      radio_type: 'modem_tcp',
      modem_tcp: { host: 'modem.local', port: 5055 },
    });
    await flushPromises();

    await buttonWithText(wrapper, 'Edit Settings')!.trigger('click');
    const tokenInput = wrapper.find('input[type="password"]');
    expect(tokenInput.exists()).toBe(true);
    await tokenInput.setValue('new-user-token');
    await buttonWithText(wrapper, 'Save Changes')!.trigger('click');
    await flushPromises();

    expect(ApiService.importConfig).toHaveBeenCalledWith({
      radio_type: 'modem_tcp',
      modem_tcp: { host: 'modem.local', port: 5055, token: 'new-user-token' },
    });
  });
});
