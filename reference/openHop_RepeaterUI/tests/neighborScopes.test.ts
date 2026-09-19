import { beforeEach, describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import type { VueWrapper } from '@vue/test-utils';
import { describeScopes, parseScopeNames } from '@/utils/neighborScopes';
import type { NeighborScopeRecord } from '@/generated/openapi';

// NeighborTable pulls in a store, and @vue/devtools-kit reads localStorage the
// moment pinia is imported. Under Node's own experimental localStorage — which
// shadows jsdom's here — that read throws and takes the whole file down before a
// test runs. Stub it, then import the component dynamically so the stub is in
// place first. Harmless once the environment provides a real one.
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
const { createPinia, setActivePinia } = await import('pinia');
const { default: NeighborTable } = await import('@/components/neighbors/NeighborTable.vue');

const NOW = 1785372000; // fixed epoch seconds; only relative ordering matters here

function record(overrides: Partial<NeighborScopeRecord> = {}): NeighborScopeRecord {
  return {
    scopes: 'DEN,BOU',
    status: 'responded',
    queried_at: NOW,
    responded_at: NOW,
    ...overrides,
  };
}

const advert = (pubkey: string, extra: Record<string, unknown> = {}) => ({
  id: 1,
  timestamp: NOW,
  pubkey,
  node_name: 'repeater-one',
  is_repeater: true,
  route_type: 2,
  contact_type: 'Repeater',
  latitude: null,
  longitude: null,
  first_seen: NOW,
  last_seen: NOW,
  rssi: -90,
  snr: 6,
  advert_count: 12,
  is_new_neighbor: false,
  zero_hop: true,
  ...extra,
});

describe('parseScopeNames', () => {
  it('splits, trims and drops empties', () => {
    expect(parseScopeNames(' DEN , BOU ,, ')).toEqual(['DEN', 'BOU']);
  });

  it('strips the leading # the transport-key table stores', () => {
    expect(parseScopeNames('#DEN,#BOU')).toEqual(['DEN', 'BOU']);
  });

  it('treats an empty or missing string as no scopes', () => {
    expect(parseScopeNames('')).toEqual([]);
    expect(parseScopeNames(null)).toEqual([]);
  });
});

describe('describeScopes', () => {
  it('reports a never-queried neighbour distinctly from a failed query', () => {
    const never = describeScopes(null);
    const failed = describeScopes(record({ scopes: '', status: 'timeout', responded_at: null }));

    expect(never.state).toBe('unknown');
    expect(never.label).toBe('—');
    expect(failed.state).toBe('failed');
    expect(failed.label).toBe('⚠');
  });

  it('counts scopes in the label and lists them in the tooltip', () => {
    const display = describeScopes(record());

    expect(display.state).toBe('scoped');
    expect(display.label).toBe('2');
    expect(display.names).toEqual(['DEN', 'BOU']);
    expect(display.title).toContain('DEN, BOU');
  });

  it('treats an empty answer as the unscoped wildcard, not as missing data', () => {
    const display = describeScopes(record({ scopes: '' }));

    expect(display.state).toBe('unscoped');
    expect(display.label).toBe('*');
    expect(display.stale).toBe(false);
  });

  it('keeps showing an earlier answer after a failed query, flagged stale', () => {
    // The responder rate-limits anon replies, so one timeout is weak evidence
    // that the scopes changed — but it must not read as a fresh answer either.
    const display = describeScopes(
      record({ status: 'timeout', queried_at: NOW + 3600, responded_at: NOW }),
    );

    expect(display.state).toBe('scoped');
    expect(display.names).toEqual(['DEN', 'BOU']);
    expect(display.stale).toBe(true);
    expect(display.title).toContain('no reply');
  });

  it('names a send failure rather than reporting it as no reply', () => {
    const display = describeScopes(
      record({ scopes: '', status: 'send_failed', responded_at: null }),
    );

    expect(display.state).toBe('failed');
    expect(display.title).toContain('could not send');
  });
});

/** The scopes column is the last cell in the row, by design — it is the far-right column. */
const lastCell = (wrapper: VueWrapper) => {
  const cells = wrapper.findAll('tbody td');
  return cells[cells.length - 1];
};

describe('NeighborTable scopes column', () => {
  // NeighborTable reads the noise floor from the system store for its signal bars.
  beforeEach(() => setActivePinia(createPinia()));

  const baseProps = {
    contactType: 'Repeater',
    contactTypeKey: '2',
    originalCount: 1,
    color: '#0f0',
  };

  it('is absent unless the table opts in', () => {
    const wrapper = mount(NeighborTable, {
      props: { ...baseProps, adverts: [advert('aa'.repeat(32))] },
    });

    expect(wrapper.find('thead').text()).not.toContain('Scopes');
  });

  it('renders the stored state per row, matched case-insensitively on pubkey', () => {
    const pubkey = 'AA'.repeat(32);
    const wrapper = mount(NeighborTable, {
      props: {
        ...baseProps,
        adverts: [advert(pubkey)],
        showScopes: true,
        scopes: { [pubkey.toLowerCase()]: record() },
      },
    });

    expect(wrapper.find('thead').text()).toContain('Scopes');
    const cell = lastCell(wrapper);
    expect(cell.text()).toBe('2');
    expect(cell.find('button').attributes('title')).toContain('DEN, BOU');
  });

  it('shows the placeholder for a repeater with no stored record', () => {
    const wrapper = mount(NeighborTable, {
      props: { ...baseProps, adverts: [advert('bb'.repeat(32))], showScopes: true, scopes: {} },
    });

    expect(lastCell(wrapper).text()).toBe('—');
  });

  it('emits show-scopes without emitting show-details for the row click', () => {
    const pubkey = 'cc'.repeat(32);
    const wrapper = mount(NeighborTable, {
      props: {
        ...baseProps,
        adverts: [advert(pubkey)],
        showScopes: true,
        scopes: { [pubkey]: record() },
      },
    });

    lastCell(wrapper).find('button').trigger('click');

    expect(wrapper.emitted('show-scopes')).toHaveLength(1);
    expect(wrapper.emitted('show-details')).toBeUndefined();
  });
});

describe('scope query result → stored state', () => {
  // The bug this covers: the repeater deliberately keeps a neighbour's last good
  // answer when a later query fails, so a response that reports the failure must
  // still carry those scopes — and the merge must not blank them. Nothing tested
  // the response → store → display path, only hand-built records.
  const merge = (result: {
    pubkey: string;
    status: NeighborScopeRecord['status'];
    scopes: string;
    queried_at?: number | null;
    responded_at?: number | null;
  }): NeighborScopeRecord => ({
    scopes: result.scopes,
    status: result.status,
    queried_at: result.queried_at as number,
    responded_at: result.responded_at ?? null,
  });

  it('keeps a rate-limited repeater showing its scopes, flagged stale', () => {
    const merged = merge({
      pubkey: 'aa'.repeat(32),
      status: 'timeout',
      scopes: 'DEN,BOU', // the repeater returns what it still has on record
      queried_at: NOW + 3600,
      responded_at: NOW,
    });

    const display = describeScopes(merged);
    expect(display.state).toBe('scoped');
    expect(display.label).toBe('2');
    expect(display.stale).toBe(true);
  });

  it('reports a first-ever query that got no reply as failed, not as unscoped', () => {
    const display = describeScopes(
      merge({ pubkey: 'bb'.repeat(32), status: 'timeout', scopes: '', queried_at: NOW }),
    );

    expect(display.state).toBe('failed');
    expect(display.label).toBe('⚠');
  });

  it('records a duty-cycle refusal as asked, so it stops reading as never queried', () => {
    const display = describeScopes(
      merge({ pubkey: 'cc'.repeat(32), status: 'send_failed', scopes: '', queried_at: NOW }),
    );

    expect(display.state).toBe('failed');
    expect(display.title).toContain('could not send');
  });
});

describe('wildcard-only answers', () => {
  // A repeater may answer with a literal `*` instead of an empty string; both mean
  // "unscoped traffic only", so neither may render as a scope named `*`.
  it('treats a lone * as unscoped, not as one scope', () => {
    const display = describeScopes(record({ scopes: '*' }));

    expect(display.state).toBe('unscoped');
    expect(display.label).toBe('*');
    expect(display.names).toEqual([]);
    expect(display.summary).toBe('Unscoped only');
  });

  it('treats a repeated wildcard the same way', () => {
    expect(describeScopes(record({ scopes: '*, *' })).state).toBe('unscoped');
  });

  it('still counts a real scope listed alongside the wildcard', () => {
    const display = describeScopes(record({ scopes: 'DEN,*' }));

    expect(display.state).toBe('scoped');
    expect(display.names).toEqual(['DEN', '*']);
  });
});

describe('NeighborMenu icon alignment', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('sizes the Query Scopes icon like every other item in the menu', async () => {
    const { default: NeighborMenu } = await import('@/components/ui/NeighborMenu.vue');
    const wrapper = mount(NeighborMenu, {
      props: { neighbor: { id: 1, pubkey: 'aa'.repeat(32) }, canQueryScopes: true },
      attachTo: document.body,
    });
    await wrapper.find('button').trigger('click');

    const icons = [...document.querySelectorAll('body > div button svg')];
    expect(icons.length).toBeGreaterThan(1);
    // A width/height attribute on one icon and not the others is what knocked the
    // label out of line, so no menu icon may carry intrinsic dimensions.
    for (const icon of icons) {
      expect(icon.getAttribute('width')).toBeNull();
      expect(icon.getAttribute('height')).toBeNull();
      expect(icon.getAttribute('class')).toContain('w-4 h-4');
    }
    wrapper.unmount();
  });

  it('left-aligns every item so a wrapped label cannot centre itself', async () => {
    // A <button> is text-align:center by default and Tailwind's preflight does not
    // reset it, so "Query Scopes" wrapping in the 144px-wide menu rendered as two
    // centred lines that read as an indent. Width now fits it, and text-left keeps
    // any future long label aligned with its neighbours.
    const { default: NeighborMenu } = await import('@/components/ui/NeighborMenu.vue');
    const wrapper = mount(NeighborMenu, {
      props: { neighbor: { id: 1, pubkey: 'bb'.repeat(32) }, canQueryScopes: true },
      attachTo: document.body,
    });
    await wrapper.find('button').trigger('click');

    const panel = document.querySelector('body > div.fixed')!;
    const items = [...panel.querySelectorAll('button')];
    expect(items).toHaveLength(4);
    for (const item of items) {
      expect(item.getAttribute('class')).toContain('text-left');
    }
    wrapper.unmount();
  });

  it('keeps the positioning width in step with the rendered menu width', async () => {
    // The mobile overflow check needs the width before the menu exists, so the
    // constant mirrors the utility class; a drift between them mispositions the
    // menu near the right edge.
    const source = await import('@/components/ui/NeighborMenu.vue?raw');
    const text = source.default as string;
    const constant = /MENU_WIDTH_PX = (\d+)/.exec(text)?.[1];
    const utility = /class="fixed w-(\d+) /.exec(text)?.[1];
    expect(constant).toBeDefined();
    expect(utility).toBeDefined();
    // Tailwind spacing: w-<n> is n * 0.25rem at the default 16px root font size.
    expect(Number(constant)).toBe(Number(utility) * 4);
  });
});

describe('NeighborScopesModal scope badges', () => {
  beforeEach(() => setActivePinia(createPinia()));

  const mountModal = async (props: Record<string, unknown>) => {
    const { default: NeighborScopesModal } = await import(
      '@/components/modals/NeighborScopesModal.vue'
    );
    return mount(NeighborScopesModal, {
      props: {
        show: true,
        neighbor: { pubkey: 'aa'.repeat(32), node_name: 'peer', zero_hop: true },
        ...props,
      },
      attachTo: document.body,
    });
  };

  const badges = () => [...document.querySelectorAll('.modal-backdrop span.rounded-full')];

  it('greens a scope we also serve and leaves it with no add button', async () => {
    const wrapper = await mountModal({
      record: record({ scopes: 'DEN,BOU' }),
      servedScopes: ['*', 'DEN'],
    });

    const den = badges().find((b) => b.textContent?.includes('DEN'))!;
    const bou = badges().find((b) => b.textContent?.includes('BOU'))!;

    expect(den.getAttribute('class')).toContain('text-accent-green');
    expect(den.querySelector('button')).toBeNull();
    // Not shared: blue, with a + to start serving it.
    expect(bou.getAttribute('class')).toContain('text-primary');
    expect(bou.querySelector('button')).not.toBeNull();
    wrapper.unmount();
  });

  it('emits the scope name when + is pressed', async () => {
    const wrapper = await mountModal({
      record: record({ scopes: 'BOU' }),
      servedScopes: ['*'],
    });

    const button = badges()
      .find((b) => b.textContent?.includes('BOU'))!
      .querySelector('button')!;
    button.dispatchEvent(new Event('click'));
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('add-scope')).toEqual([['BOU']]);
    wrapper.unmount();
  });

  it('never offers to add the wildcard, which is not a region', async () => {
    // `*` is this node's own unscoped-flood switch and has no transport key, so a
    // + on it would post a region named "*".
    const wrapper = await mountModal({
      record: record({ scopes: 'DEN,*' }),
      servedScopes: [],
    });

    const wildcard = badges().find((b) => b.textContent?.trim().startsWith('*'))!;
    expect(wildcard.querySelector('button')).toBeNull();
    wrapper.unmount();
  });

  it('disables every + while one add is in flight', async () => {
    const wrapper = await mountModal({
      record: record({ scopes: 'DEN,BOU' }),
      servedScopes: [],
      addingScope: 'DEN',
    });

    const buttons = [...document.querySelectorAll('.modal-backdrop span.rounded-full button')];
    expect(buttons).toHaveLength(2);
    for (const button of buttons) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    wrapper.unmount();
  });
});
