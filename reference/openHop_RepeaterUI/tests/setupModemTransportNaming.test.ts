import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useSetupStore } from '@/stores/setup';
import {
  normalizeModemHardwareOptions,
  normalizeModemTransportConfig,
} from '@/utils/modemTransport';

const radioPreset = {
  title: 'EU',
  description: 'EU preset',
  frequency: '869.525',
  spreading_factor: '8',
  bandwidth: '62.5',
  coding_rate: '8',
  tx_power: '14',
};

function setupStoreForCompletion() {
  const store = useSetupStore();
  store.currentStep = 6;
  store.nodeName = 'repeater';
  store.selectedRadioPreset = radioPreset;
  store.adminPassword = 'secret-password';
  store.confirmPassword = 'secret-password';
  return store;
}

describe('setup modem transport naming', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
  });

  it('normalizes legacy hardware options to canonical keys and openHop Modem labels', () => {
    expect(
      normalizeModemHardwareOptions([
        {
          key: 'pymc_tcp',
          name: 'pyMC TCP modem',
          description: 'legacy TCP transport',
          config: { radio_type: 'pymc_tcp' },
        },
        {
          key: 'pymc_usb',
          name: 'pyMC USB modem',
          description: 'legacy USB transport',
          config: { radio_type: 'pymc_usb' },
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        key: 'modem_tcp',
        name: 'openHop Modem (Wi-Fi / Ethernet)',
        config: expect.objectContaining({ radio_type: 'modem_tcp' }),
      }),
      expect.objectContaining({
        key: 'modem_usb',
        name: 'openHop Modem (USB-CDC)',
        config: expect.objectContaining({ radio_type: 'modem_usb' }),
      }),
    ]);
  });

  it('hydrates legacy sections canonically, prefers canonical values, and never hydrates tokens', () => {
    expect(
      normalizeModemTransportConfig({
        radio_type: 'pymc_tcp',
        pymc_tcp: { host: 'legacy.local', port: 5055, token: 'legacy-secret' },
        modem_tcp: { host: 'canonical.local', port: 6000, token: 'canonical-secret' },
      }),
    ).toEqual({
      radio_type: 'modem_tcp',
      modem_tcp: { host: 'canonical.local', port: 6000 },
    });
  });

  it('keeps the canonical hardware option when both canonical and legacy forms are returned', () => {
    expect(
      normalizeModemHardwareOptions([
        {
          key: 'pymc_tcp',
          name: 'legacy option',
          description: 'legacy',
          config: { radio_type: 'pymc_tcp', pymc_tcp: { host: 'legacy.local' } },
        },
        {
          key: 'modem_tcp',
          name: 'canonical option',
          description: 'canonical',
          config: { radio_type: 'modem_tcp', modem_tcp: { host: 'canonical.local' } },
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        key: 'modem_tcp',
        config: expect.objectContaining({
          radio_type: 'modem_tcp',
          modem_tcp: { host: 'canonical.local' },
        }),
      }),
    ]);
  });

  it('submits canonical setup fields and omits a blank token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ success: true }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const store = setupStoreForCompletion();
    store.selectedHardware = {
      key: 'modem_tcp',
      name: 'openHop Modem (Wi-Fi / Ethernet)',
      description: 'Network modem',
      config: { radio_type: 'modem_tcp' },
    };
    store.tcpHost = 'modem.local';
    store.tcpPort = 6000;
    store.tcpToken = '   ';

    await store.completeSetup();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toMatchObject({
      hardware_key: 'modem_tcp',
      modem_tcp_host: 'modem.local',
      modem_tcp_port: 6000,
    });
    expect(body).not.toHaveProperty('modem_tcp_token');
    expect(Object.keys(body).some((key) => key.startsWith('pymc_'))).toBe(false);
  });

  it('submits a canonical token only when the user intentionally enters one', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ success: true }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const store = setupStoreForCompletion();
    store.selectedHardware = {
      key: 'modem_tcp',
      name: 'openHop Modem (Wi-Fi / Ethernet)',
      description: 'Network modem',
      config: { radio_type: 'modem_tcp' },
    };
    store.tcpHost = 'modem.local';
    store.tcpToken = 'new-user-token';

    await store.completeSetup();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.modem_tcp_token).toBe('new-user-token');
  });
});
