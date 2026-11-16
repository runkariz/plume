import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import {
  ApiError,
  type ChangesQuery,
  type ChangeTotals,
  type PublicBuild,
  type PublicChange,
} from '@/api/types';
import { Button, Card, Chip, ErrorState, LoadingState } from '@/components';
import { formatDate } from '@/lib/format';
import { ChangeBrief, subjectOf } from './ChangeBrief';

/** The filters of the list. */
export const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'breaking', label: 'Breaking' },
  { id: 'endpoints', label: 'Endpoints' },
  { id: 'fields', label: 'Fields' },
  { id: 'auth', label: 'Auth' },
  { id: 'wording', label: 'Wording only' },
] as const;
export type FilterId = (typeof FILTERS)[number]['id'];

/** The kinds a filter covers. The server matches one kind exactly, so a group is filtered here, over what it sends. */
export const KINDS: Record<'endpoints' | 'fields' | 'auth', string[]> = {
  endpoints: ['endpoint', 'webhook_event'],
  fields: ['param', 'request_field', 'response_field', 'model', 'property'],
  auth: ['auth_scheme', 'scope'],
};

export const isGroup = (f: FilterId): f is 'endpoints' | 'fields' | 'auth' =>
  f === 'endpoints' || f === 'fields' || f === 'auth';

/** What to ask the server for a filter (a kind group asks for everything but wording: the rest is done here). */
export function filterQuery(f: FilterId): Pick<ChangesQuery, 'breaking' | 'wordingOnly'> {
  if (f === 'breaking') return { breaking: true, wordingOnly: false };
  if (f === 'wording') return { wordingOnly: true };
  return { wordingOnly: false };
}

/**
 * The count a filter chip shows. `totals` are those of the WHOLE build without its wording-only changes (asked with
 * wordingOnly=false and no other filter), so every chip shows what its list shows, whichever filter is on; the
 * wording-only count comes from the timeline.
 */
export function filterCount(f: FilterId, t: ChangeTotals, wording = 0): number | null {
  const sum = (kinds: string[]) => kinds.reduce((n, k) => n + (t.byKind?.[k] ?? 0), 0);
  switch (f) {
    case 'all':
      return t.confirmed + t.likely;
    case 'breaking':
      return t.breaking;
    case 'wording':
      return wording;
    default:
      return t.byKind ? sum(KINDS[f]) : null;
  }
}

const PAGE = 100;
/** A kind group reads the build in pages of 200 up to this many, then says it stopped. */
const GROUP_PAGES = 10;

function countsText(b: PublicBuild): string {
  const c = b.counts;
  const real = Math.max(0, c.confirmed + c.likely - c.wordingOnly);
  if (real === 0 && c.wordingOnly === 0) return 'No API changes found';
  const parts = [`${real} ${real === 1 ? 'change' : 'changes'}`];
  if (c.wordingOnly) parts.push(`${c.wordingOnly} wording only`);
  return parts.join(' · ');
}

/** The groups of a page of changes by document, in the order they first appear (the server's order). */
export function groupByDocument(
  items: PublicChange[],
): { key: string; title: string; items: PublicChange[] }[] {
  const groups = new Map<string, { key: string; title: string; items: PublicChange[] }>();
  for (const i of items) {
    const key = i.subject.docId ?? `${i.kind}:${i.subject.path ?? i.subject.model ?? i.id}`;
    const g = groups.get(key) ?? { key, title: subjectOf(i), items: [] };
    g.items.push(i);
    groups.set(key, g);
  }
  return [...groups.values()];
}

type Loaded = {
  status: 'ready';
  items: PublicChange[];
  next: number | null;
  computedAt: string | null;
  /** A kind group stopped reading after GROUP_PAGES pages. */
  truncated: boolean;
};
type State =
  { status: 'loading' } | { status: 'error'; message: string; notFound: boolean } | Loaded;

/**
 * The Changes tab of an API: the builds with notes (newest first, counts, BREAKING), and the list of one build:
 * filter chips (counts for the whole selection), items grouped by document, wording-only ones kept apart, and an Atom
 * link. The build, the filter, the search and the highlighted change are in the URL.
 */
export function ChangesTab({ api, builds }: { api: string; builds: PublicBuild[] }) {
  const client = useApiClient();
  const [params, setParams] = useSearchParams();
  const wanted = params.get('build');
  const build = builds.find((b) => b.build === wanted) ?? builds[0];
  const rawFilter = params.get('filter');
  const filter: FilterId = FILTERS.some((f) => f.id === rawFilter)
    ? (rawFilter as FilterId)
    : 'all';
  const q = params.get('q') ?? '';
  const item = params.get('item');

  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
    }
    next.set('section', 'changes');
    setParams(next, { replace: true });
  };

  const [state, setState] = useState<State>({ status: 'loading' });
  const [totals, setTotals] = useState<ChangeTotals | null>(null);
  const [more, setMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [search, setSearch] = useState(q);
  const buildId = build?.build;

  // the counts of the whole build, once per build: the chips never change with the filter
  useEffect(() => {
    if (!buildId) return;
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset when the build changes
    setTotals(null);
    client
      .getChanges(api, { build: buildId, wordingOnly: false, limit: 1 }, ctrl.signal)
      .then((p) => setTotals(p.totals))
      .catch(() => undefined); // the chips just show no count
    return () => ctrl.abort();
  }, [client, api, buildId]);

  const base = useCallback(
    (cursor?: number | null): ChangesQuery => ({
      build: buildId,
      ...filterQuery(filter),
      q,
      cursor,
      limit: isGroup(filter) ? 200 : PAGE,
    }),
    [buildId, filter, q],
  );

  useEffect(() => {
    if (!buildId) return;
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reload when the build, filter or search changes
    setState({ status: 'loading' });
    (async () => {
      let items: PublicChange[] = [];
      let cursor: number | null = null;
      let computedAt: string | null = null;
      let pages = 0;
      let truncated = false;
      for (;;) {
        const p = await client.getChanges(api, base(cursor), ctrl.signal);
        computedAt = p.computedAt ?? computedAt;
        items = [...items, ...p.items];
        cursor = p.nextCursor;
        pages += 1;
        // a group reads on until its page of 100 is full or the build ends
        if (!isGroup(filter) || cursor === null) break;
        const want = items.filter((i) => KINDS[filter].includes(i.kind)).length;
        if (want >= PAGE) break;
        if (pages >= GROUP_PAGES) {
          truncated = true;
          break;
        }
      }
      if (isGroup(filter)) items = items.filter((i) => KINDS[filter].includes(i.kind));
      setState({ status: 'ready', items, next: cursor, computedAt, truncated });
    })().catch((e: unknown) => {
      if (ctrl.signal.aborted) return;
      setState({
        status: 'error',
        message: e instanceof Error && e.message ? e.message : 'Could not load the changes.',
        notFound: e instanceof ApiError && e.status === 404,
      });
    });
    return () => ctrl.abort();
  }, [client, api, base, buildId, filter]);

  // the search box is typed freely; the URL follows a moment later
  useEffect(() => {
    const t = setTimeout(() => {
      if (search !== q) set({ q: search || null });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function showMore() {
    if (state.status !== 'ready' || state.next === null) return;
    setMore(true);
    setMoreError(null);
    try {
      let items: PublicChange[] = [];
      let cursor: number | null = state.next;
      let pages = 0;
      let truncated = false;
      for (;;) {
        const p = await client.getChanges(api, base(cursor));
        items = [...items, ...p.items];
        cursor = p.nextCursor;
        pages += 1;
        if (!isGroup(filter) || cursor === null) break;
        if (items.filter((i) => KINDS[filter].includes(i.kind)).length >= PAGE) break;
        if (pages >= GROUP_PAGES) {
          truncated = true;
          break;
        }
      }
      if (isGroup(filter)) items = items.filter((i) => KINDS[filter].includes(i.kind));
      setState({ ...state, items: [...state.items, ...items], next: cursor, truncated });
    } catch (e) {
      setMoreError(e instanceof Error && e.message ? e.message : 'Could not load more changes.');
    } finally {
      setMore(false);
    }
  }

  const atom = `${client.baseUrl}/v1/apis/${encodeURIComponent(api)}/changes.atom`;

  if (!build)
    return (
      <Card className="pad">
        <p className="muted">No API changes found.</p>
      </Card>
    );
  const items = state.status === 'ready' ? state.items : [];
  const groups = groupByDocument(items);
  const wordingTotal = build.counts.wordingOnly;
  const when = build.docsAsOf ? formatDate(build.docsAsOf) : build.build;

  return (
    <div className="stack changes-tab">
      <Card className="pad" role="region" aria-label="Builds with changes">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 className="h2-sm">Changes</h2>
          <a className="small" href={atom} rel="alternate" type="application/atom+xml">
            Subscribe (Atom)
          </a>
        </div>
        <ul className="plain build-timeline" aria-label="Builds">
          {builds.map((b) => {
            const on = b.build === build.build;
            return (
              <li key={b.build} className={on ? 'on' : undefined}>
                <button
                  type="button"
                  className="linkbtn"
                  aria-current={on ? 'true' : undefined}
                  onClick={() => set({ build: b.build, item: null, filter: null, q: null })}
                >
                  {b.docsAsOf ? formatDate(b.docsAsOf) : b.build}
                </button>{' '}
                {b.latest ? <Chip tone="ok">latest</Chip> : null}{' '}
                {b.counts.breaking > 0 ? (
                  <Chip tone="bad">
                    <span aria-hidden="true">⚠ </span>Breaking
                  </Chip>
                ) : null}{' '}
                <span className="muted small">{countsText(b)}</span>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card className="pad" role="region" aria-label={`Changes of ${when}`}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }} role="group" aria-label="Filter">
          {FILTERS.map((f) => {
            const n = totals ? filterCount(f.id, totals, build.counts.wordingOnly) : null;
            return (
              <button
                key={f.id}
                type="button"
                className={`pill${filter === f.id ? ' on' : ''}`}
                aria-pressed={filter === f.id}
                onClick={() => set({ filter: f.id === 'all' ? null : f.id, item: null })}
              >
                {f.label}
                {n !== null ? <span className="faint small"> {n}</span> : null}
              </button>
            );
          })}
        </div>
        <label className="small" htmlFor="changes-q" style={{ display: 'block', marginTop: 10 }}>
          Search the changes (path, model or field)
        </label>
        <input
          id="changes-q"
          className="input"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {state.status === 'ready' && state.computedAt ? (
          <p className="faint small">Recomputed {state.computedAt.slice(11, 16)} UTC</p>
        ) : null}

        {state.status === 'loading' ? <LoadingState label="Loading the changes" /> : null}
        {state.status === 'error' ? (
          state.notFound ? (
            <p className="muted">No notes for this build.</p>
          ) : (
            <ErrorState message={state.message} />
          )
        ) : null}
        {state.status === 'ready' ? (
          <>
            {item && !items.some((i) => i.id === item) && state.next === null ? (
              <p className="muted small" role="status">
                That change is no longer listed: the notes were recomputed.
              </p>
            ) : null}
            {items.length === 0 ? (
              <p className="muted" role="status">
                {filter === 'all' && !q ? 'No API changes found.' : 'No changes match this filter.'}
              </p>
            ) : (
              groups.map((g) => (
                <section key={g.key} className="change-group" aria-label={g.title}>
                  <h3 className="h3-sm mono">{g.title}</h3>
                  <ul className="plain stack">
                    {g.items.map((i) => (
                      <ChangeBrief key={i.id} api={api} item={i} highlighted={i.id === item} />
                    ))}
                  </ul>
                </section>
              ))
            )}
            {state.next !== null ? (
              <p>
                <Button disabled={more} onClick={() => void showMore()}>
                  {more ? 'Loading…' : 'Show more'}
                </Button>
              </p>
            ) : null}
            {state.truncated && state.next !== null ? (
              <p className="faint small">Stopped reading here: use the search to narrow it.</p>
            ) : null}
            {moreError ? (
              <p role="alert" className="form-error small">
                {moreError}
              </p>
            ) : null}
            {filter !== 'wording' && wordingTotal > 0 ? (
              <p className="small muted wording-note">
                Wording only: {wordingTotal} {wordingTotal === 1 ? 'description' : 'descriptions'}{' '}
                changed.{' '}
                <button
                  type="button"
                  className="linkbtn"
                  onClick={() => set({ filter: 'wording', item: null })}
                >
                  Show them
                </button>
              </p>
            ) : null}
          </>
        ) : null}
        <p className="faint small">
          Changes come from the vendor&apos;s docs.{' '}
          <Link to={`/apis/${encodeURIComponent(api)}`}>Back to the API</Link>
        </p>
      </Card>
    </div>
  );
}
