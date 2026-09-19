import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('@/utils/api', () => ({
  default: {
    get: apiGet,
    post: apiPost,
  },
}));

import WebSettings from '@/components/configuration/WebSettings.vue';
import { useSystemStore } from '@/stores/system';

describe('Web settings CARTO API key', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiGet.mockReset().mockImplementation(async (url: string) => {
      if (url.includes('web_frontends')) {
        return {
          success: true,
          data: {
            selected_id: 'builtin',
            frontends: [
              {
                id: 'builtin',
                kind: 'builtin',
                name: 'Default Frontend',
                description: 'Built-in',
                path: null,
                version: '1.0.0',
                available: true,
                enabled: true,
                selected: true,
              },
              {
                id: 'console',
                kind: 'console',
                name: 'openHop Console',
                description: 'Console',
                path: '/opt/pymc_console/web/html',
                version: null,
                available: false,
                enabled: false,
                selected: false,
              },
            ],
          },
        };
      }
      return { success: true, data: { exists: false } };
    });
    apiPost.mockReset().mockResolvedValue({ success: true, data: {} });

    useSystemStore().stats = {
      version: 'test',
      core_version: 'test',
      config: {
        web: {
          cors_enabled: false,
          web_path: null,
          carto_api_key: 'configured-key',
        },
      },
    };
  });

  it('loads the configured key and saves an updated key to the web config', async () => {
    const wrapper = mount(WebSettings);
    await flushPromises();

    const input = wrapper.get('[data-testid="carto-api-key"]');
    expect(input.attributes('type')).toBe('password');
    expect((input.element as HTMLInputElement).value).toBe('configured-key');

    await input.setValue('replacement-key');
    await wrapper.get('[data-testid="save-carto-api-key"]').trigger('click');
    await flushPromises();

    expect(apiPost).toHaveBeenLastCalledWith('/update_web_config', {
      web: {
        cors_enabled: false,
        site_name: '',
        carto_api_key: 'replacement-key',
        web_path: null,
      },
    });
  });

  it('can clear the configured key', async () => {
    const wrapper = mount(WebSettings);
    await flushPromises();

    await wrapper.get('[data-testid="clear-carto-api-key"]').trigger('click');
    await flushPromises();

    expect(apiPost).toHaveBeenLastCalledWith('/update_web_config', {
      web: {
        cors_enabled: false,
        site_name: '',
        carto_api_key: '',
        web_path: null,
      },
    });
  });
});
