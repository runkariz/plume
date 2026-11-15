import type { ModelSnapshot, ModelWarning } from '@/api/types';
import { mappingRows } from './graph';

/** Where the review banner's "see the list" link goes (the id of the list on the model page). */
export const WARNINGS_ID = 'model-warnings';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The sentence for the warnings of one code ("3 mappings cite only a request body"); unknown codes read generically. */
export function warningSummary(code: string, items: ModelWarning[]): string {
  const n = items.length;
  if (code === 'WRITE_ONLY_SOURCE')
    return `${plural(n, 'mapping cites', 'mappings cite')} only a request body`;
  return `${plural(n, 'warning', 'warnings')}: ${code.toLowerCase().replace(/_/g, ' ')}`;
}

export interface WarningGroup {
  code: string;
  items: ModelWarning[];
  summary: string;
}

/** The warnings of a model grouped by code, in the order the server sent them. */
export function groupWarnings(warnings: ModelWarning[] | undefined): WarningGroup[] {
  const by = new Map<string, ModelWarning[]>();
  for (const w of warnings ?? []) by.set(w.code, [...(by.get(w.code) ?? []), w]);
  return [...by.entries()].map(([code, items]) => ({
    code,
    items,
    summary: warningSummary(code, items),
  }));
}

/** The warnings that belong to one mapping (a field of an API); a warning without an API belongs to the field. */
export function warningsFor(snap: ModelSnapshot, field: string, apiId: string): ModelWarning[] {
  return (snap.warnings ?? []).filter((w) => w.field === field && (!w.api || w.api === apiId));
}

/**
 * The query string that opens the mapping a warning is about (`?field=..&api=..`), or null when the model has no such
 * mapping any more (a warning is data from the server: never link to something that is not there).
 */
export function warningSearch(snap: ModelSnapshot, w: ModelWarning): string | null {
  if (!w.field) return null;
  const row = mappingRows(snap).find((r) => r.field === w.field && (!w.api || r.apiId === w.api));
  return row
    ? `?field=${encodeURIComponent(row.field)}&api=${encodeURIComponent(row.apiId)}`
    : null;
}
