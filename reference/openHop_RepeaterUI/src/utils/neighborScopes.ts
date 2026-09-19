import type { NeighborScopeRecord } from '@/generated/openapi';
import { formatTimeAgo } from '@/utils/formatters';

/**
 * Display state for a neighbour's region scopes.
 *
 * `unknown` and `failed` look alike in the data — both mean we have no scope
 * names — but they are different facts about the mesh, so the table draws them
 * differently: `unknown` is a repeater nobody has asked, `failed` is one that was
 * asked and did not answer (multi-hop, off the air, or rate-limited).
 */
export type ScopeState = 'unknown' | 'scoped' | 'unscoped' | 'failed';

export interface ScopeDisplay {
  state: ScopeState;
  /** Scope names from the neighbour's last answer, '#' stripped. */
  names: string[];
  /** True when the names come from an older answer and the last query failed. */
  stale: boolean;
  /** Cell glyph: the scope count, the unscoped wildcard, or a placeholder. */
  label: string;
  /** Short prose for layouts with room for it (mobile cards, the panel header). */
  summary: string;
  title: string;
}

/** How the repeater spells "no region" — matching the wildcard the MQTT payload uses. */
export const UNSCOPED_WILDCARD = '*';

const STATUS_LABELS: Record<string, string> = {
  timeout: 'no reply',
  send_failed: 'could not send',
};

/** Split the repeater's comma-separated scope string into names. */
export function parseScopeNames(scopes: string | null | undefined): string[] {
  return (scopes || '')
    .split(',')
    .map((name) => name.trim())
    // The transport-key table stores region names with a leading '#', which is
    // not part of the name; the repeater strips it on the way out, so this is
    // belt-and-braces for an older repeater that did not.
    .map((name) => (name.startsWith('#') ? name.slice(1).trim() : name))
    .filter((name) => name.length > 0);
}

function ageSuffix(at: number | null | undefined): string {
  if (!at) return '';
  return ` (${formatTimeAgo(new Date(at * 1000))})`;
}

export function describeScopes(record?: NeighborScopeRecord | null): ScopeDisplay {
  if (!record) {
    return {
      state: 'unknown',
      names: [],
      stale: false,
      label: '—',
      summary: 'Not queried',
      title: 'Scopes not queried yet',
    };
  }

  // A repeater can spell "no region" as a literal `*` scope rather than as an
  // empty string, which is the same answer — unscoped traffic only — and must not
  // read as one scope named `*`. Every-wildcard rather than a length check so a
  // repeater that repeats it (`*,*`) lands in the same place.
  const parsed = parseScopeNames(record.scopes);
  const names = parsed.every((name) => name === UNSCOPED_WILDCARD) ? [] : parsed;
  // An answer we have, even an old one, beats reporting nothing: a single failed
  // query is weak evidence that a neighbour's scopes changed, and the responder
  // rate-limits anonymous replies.
  const answered = record.status === 'responded' || record.responded_at != null;
  const stale = answered && record.status !== 'responded';

  if (!answered) {
    const reason = STATUS_LABELS[record.status] || record.status;
    return {
      state: 'failed',
      names: [],
      stale: false,
      label: '⚠',
      summary: `Query ${reason}`,
      title: `Scope query ${reason}${ageSuffix(record.queried_at)}`,
    };
  }

  const freshness = stale
    ? `; last query ${STATUS_LABELS[record.status] || record.status}${ageSuffix(record.queried_at)}`
    : '';
  const heard = `Answered${ageSuffix(record.responded_at ?? record.queried_at)}`;

  if (names.length === 0) {
    return {
      state: 'unscoped',
      names,
      stale,
      label: UNSCOPED_WILDCARD,
      summary: 'Unscoped only',
      title: `Unscoped traffic only. ${heard}${freshness}`,
    };
  }

  return {
    state: 'scoped',
    names,
    stale,
    label: String(names.length),
    summary: names.join(', '),
    title: `${names.join(', ')}. ${heard}${freshness}`,
  };
}
