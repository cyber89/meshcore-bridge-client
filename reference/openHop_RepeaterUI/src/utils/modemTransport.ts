export const LEGACY_MODEM_TRANSPORTS = {
  pymc_tcp: 'modem_tcp',
  pymc_usb: 'modem_usb',
} as const;

export type CanonicalModemTransport =
  (typeof LEGACY_MODEM_TRANSPORTS)[keyof typeof LEGACY_MODEM_TRANSPORTS];

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function canonicalModemTransport(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  const normalized = value.trim().toLowerCase();
  return LEGACY_MODEM_TRANSPORTS[normalized as keyof typeof LEGACY_MODEM_TRANSPORTS] ?? normalized;
}

function withoutHydratedToken(value: unknown): unknown {
  if (!isRecord(value)) return value;
  const section = { ...value };
  delete section.token;
  return section;
}

function normalizeOneConfig(input: UnknownRecord): UnknownRecord {
  const output = { ...input };
  if (Object.prototype.hasOwnProperty.call(input, 'radio_type')) {
    output.radio_type = canonicalModemTransport(input.radio_type);
  }

  for (const [legacyKey, canonicalKey] of Object.entries(LEGACY_MODEM_TRANSPORTS)) {
    const section = Object.prototype.hasOwnProperty.call(input, canonicalKey)
      ? input[canonicalKey]
      : input[legacyKey];
    delete output[legacyKey];
    if (section !== undefined) output[canonicalKey] = withoutHydratedToken(section);
  }

  return output;
}

/**
 * Normalize backend config for UI hydration. Canonical sections win conflicts,
 * legacy keys are removed, nested radios are normalized, and stored TCP tokens
 * are deliberately not hydrated into browser form state.
 */
export function normalizeModemTransportConfig(input: unknown): UnknownRecord {
  if (!isRecord(input)) return {};
  const output = normalizeOneConfig(input);
  if (Array.isArray(input.radios)) {
    output.radios = input.radios.map((entry) =>
      isRecord(entry) ? normalizeOneConfig(entry) : entry,
    );
  }
  return output;
}

interface HardwareOptionLike {
  key: string;
  name?: string;
  description?: string;
  config?: UnknownRecord;
}

const HARDWARE_LABELS: Record<CanonicalModemTransport, { name: string; description: string }> = {
  modem_tcp: {
    name: 'openHop Modem (Wi-Fi / Ethernet)',
    description: 'openHop Modem over Wi-Fi or Ethernet',
  },
  modem_usb: {
    name: 'openHop Modem (USB-CDC)',
    description: 'openHop Modem over USB-CDC',
  },
};

/** Normalize old hardware-option responses while presenting canonical labels. */
export function normalizeModemHardwareOptions<T extends HardwareOptionLike>(options: T[]): T[] {
  const selected = new Map<string, T>();

  for (const option of options) {
    const key = canonicalModemTransport(option.key);
    const canonicalKey = typeof key === 'string' ? key : option.key;
    const next = {
      ...option,
      key: canonicalKey,
      config: normalizeModemTransportConfig(option.config ?? {}),
    } as T;
    const labels = HARDWARE_LABELS[canonicalKey as CanonicalModemTransport];
    const labeled = labels ? ({ ...next, ...labels } as T) : next;
    const isCanonicalModemSource =
      (canonicalKey === 'modem_tcp' || canonicalKey === 'modem_usb') && option.key === canonicalKey;

    if (!selected.has(canonicalKey) || isCanonicalModemSource) {
      selected.set(canonicalKey, labeled);
    }
  }

  return [...selected.values()];
}
