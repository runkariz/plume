import type { ModelSnapshot } from '@/api/types';
import { defaultSelection, mappingRows, type Selection } from './graph';

/** What the model page shows, all of it in the URL (a link keeps the view, the filter and the selected mapping). */
export interface ModelViewState {
  view: 'table' | 'graph' | null; // null = the default for the model size
  scope: 'field' | 'all' | null;
  /** The name filter (canonical field or source path). */
  f: string;
  /** The checked APIs; null = all. Unchecked APIs are greyed out in the graph, never hidden. */
  show: string[] | null;
  selection: Selection | null;
}

export function parseModelView(p: URLSearchParams, snap: ModelSnapshot): ModelViewState {
  const view = p.get('view');
  const scope = p.get('scope');
  const ids = snap.inputs.map((a) => a.id);
  const show = (p.get('show') ?? '').split(',').filter((id) => ids.includes(id));
  const field = p.get('field');
  const api = p.get('api');
  const valid =
    field && api && mappingRows(snap).some((r) => r.field === field && r.apiId === api)
      ? { field, apiId: api }
      : null;
  return {
    view: view === 'table' || view === 'graph' ? view : null,
    scope: scope === 'field' || scope === 'all' ? scope : null,
    f: (p.get('f') ?? '').trim(),
    // all APIs checked is the default and is not written to the URL
    show: show.length > 0 && show.length < ids.length ? show : null,
    selection: valid,
  };
}

export function withModelView(base: URLSearchParams, v: ModelViewState): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of ['view', 'scope', 'f', 'show', 'field', 'api']) p.delete(k);
  if (v.view) p.set('view', v.view);
  if (v.scope) p.set('scope', v.scope);
  if (v.f) p.set('f', v.f);
  if (v.show) p.set('show', v.show.join(','));
  if (v.selection) {
    p.set('field', v.selection.field);
    p.set('api', v.selection.apiId);
  }
  return p;
}

/** The selected mapping, or the one the page opens with. */
export function effectiveSelection(snap: ModelSnapshot, v: ModelViewState): Selection | null {
  return v.selection ?? defaultSelection(snap);
}

/** Checks or unchecks one API; the last checked one cannot be unchecked (nothing would stay in focus). */
export function toggleApi(
  snap: ModelSnapshot,
  show: string[] | null,
  id: string,
  on: boolean,
): string[] | null {
  const all = snap.inputs.map((a) => a.id);
  const current = show ?? all;
  const next = on
    ? all.filter((x) => current.includes(x) || x === id)
    : current.filter((x) => x !== id);
  if (next.length === 0) return show;
  return next.length === all.length ? null : next;
}
