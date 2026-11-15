import type { SuggestQuery, SuggestScope } from '@/api/types';

/** Concepts per page. */
export const PAGE_SIZE = 24;

export type Chip = 'all' | 'every' | 'write';

/** What the suggestions page shows, all of it in the URL (a link keeps the filters). */
export interface SuggestView {
  q: string;
  only: SuggestScope;
  require: string[];
  chip: Chip;
  page: number; // 1-based
}

const SCOPES: SuggestScope[] = ['multi', 'single', 'all'];

export function parseView(p: URLSearchParams, apis: string[]): SuggestView {
  const only = p.get('only') as SuggestScope | null;
  const page = Number(p.get('page'));
  return {
    q: (p.get('q') ?? '').trim(),
    only: only && SCOPES.includes(only) ? only : 'multi',
    // only ids of the selected APIs can be required (the server answers 400 otherwise)
    require: (p.get('require') ?? '').split(',').filter((id) => id && apis.includes(id)),
    chip: p.get('inAll') === '1' ? 'every' : p.get('write') === '1' ? 'write' : 'all',
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

/** The request for a view. The chips only apply to concepts shared by several APIs. */
export function toQuery(v: SuggestView): SuggestQuery {
  const shared = v.only !== 'single';
  return {
    q: v.q || undefined,
    only: v.only,
    require: v.require.length ? v.require : undefined,
    inAll: shared && v.chip === 'every' ? true : undefined,
    writeOnly: shared && v.chip === 'write' ? true : undefined,
    limit: PAGE_SIZE,
    offset: (v.page - 1) * PAGE_SIZE,
  };
}

/** The URL parameters for a view, keeping the parameters that are not about the view (apis, regenerate, ...). */
export function withView(base: URLSearchParams, v: SuggestView): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of ['q', 'only', 'require', 'inAll', 'write', 'page']) p.delete(k);
  if (v.q) p.set('q', v.q);
  if (v.only !== 'multi') p.set('only', v.only);
  if (v.require.length) p.set('require', v.require.join(','));
  if (v.chip === 'every') p.set('inAll', '1');
  if (v.chip === 'write') p.set('write', '1');
  if (v.page > 1) p.set('page', String(v.page));
  return p;
}

/** A change of any filter goes back to the first page. */
export function changed(v: SuggestView, patch: Partial<Omit<SuggestView, 'page'>>): SuggestView {
  return { ...v, ...patch, page: 1 };
}

export function isFiltered(v: SuggestView): boolean {
  return v.q !== '' || v.require.length > 0 || v.chip !== 'all' || v.only !== 'multi';
}
