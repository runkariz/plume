import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ApiSummary } from '@/api/types';
import { Card, Chip, EmptyState, ErrorState, Logo } from '@/components';
import { DocsUpdatedBadge } from '@/components/DocsUpdatedBadge';
import { SearchIcon } from '@/icons';
import { categoryLabel, formatDate, formatScore, modelCount } from '@/lib/format';

/** Matches the mockup: 0.89 is green, 0.88 is amber. */
const RECALL_OK_MIN = 0.89;

function StatusChip({ status }: { status: ApiSummary['status'] }) {
  if (status.kind === 'updating')
    return (
      <Chip tone="acc" dot>
        Updating · {Math.round(status.progress * 100)}%
      </Chip>
    );
  if (status.kind === 'unpublished') return <Chip dot>Not published</Chip>;
  if (status.recallAt5 == null) return <Chip dot>Not evaluated</Chip>;
  return (
    <Chip tone={status.recallAt5 >= RECALL_OK_MIN ? 'ok' : 'warn'} dot>
      Recall@5 {formatScore(status.recallAt5)}
    </Chip>
  );
}

export function ApiCard({ api }: { api: ApiSummary }) {
  return (
    <article className="card api-card">
      <div className="api-top">
        <Logo text={api.logo.text} color={api.logo.color} url={api.logo.url} />
        <div>
          <h3 className="api-name">
            <Link to={`/apis/${api.id}`} className="stretched">
              {api.name}
            </Link>
          </h3>
          <span className="faint small">{categoryLabel(api.category)}</span>
        </div>
      </div>
      <div className="api-desc muted">{api.summary}</div>
      <div className="api-stats muted">
        <span>
          <b>{api.endpoints}</b> endpoints
        </span>
        <span>
          <b>{modelCount(api)}</b> models
        </span>
        <span>
          <b>{api.guides}</b> guides
        </span>
      </div>
      <div className="api-foot">
        <span>
          {api.docsAsOf ? `Docs as of ${formatDate(api.docsAsOf)}` : 'No docs published yet'}
        </span>
        <StatusChip status={api.status} />
      </div>
      <DocsUpdatedBadge api={api.id} docsUpdated={api.docsUpdated} />
    </article>
  );
}

export function Home() {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state, retry } = useAsync(load);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // "/" focuses the search box, like the hint in the mockup says.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const typing =
        t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const items = state.status === 'ready' ? state.data.items : null;

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of items ?? []) counts.set(a.category, (counts.get(a.category) ?? 0) + 1);
    return [...counts.entries()];
  }, [items]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter(
      (a) =>
        (!category || a.category === category) &&
        (!q || `${a.name} ${a.summary} ${categoryLabel(a.category)}`.toLowerCase().includes(q)),
    );
  }, [items, query, category]);

  return (
    <>
      <section className="hero">
        <div className="eyebrow">Open knowledge bases for APIs</div>
        <h1>
          Ask the docs,
          <br />
          <em>not the internet.</em>
        </h1>
        <p className="lead" style={{ marginTop: 20 }}>
          Plume turns API documentation into searchable knowledge for developers and for Claude
          Code. Pick an API to see what it knows.
        </p>
        <div className="searchbar hero-search" role="search">
          <SearchIcon aria-hidden />
          <input
            ref={searchRef}
            type="search"
            aria-label="Search APIs"
            placeholder="Search APIs"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd aria-hidden>/</kbd>
        </div>
        {items && items.length > 0 ? (
          <div className="pills filter-row" role="group" aria-label="Filter by category">
            <button
              type="button"
              className="pillf"
              aria-pressed={category === null}
              onClick={() => setCategory(null)}
            >
              All · {items.length}
            </button>
            {categories.map(([name, count]) => (
              <button
                key={name}
                type="button"
                className="pillf"
                aria-pressed={category === name}
                onClick={() => setCategory(name)}
              >
                {categoryLabel(name)} · {count}
              </button>
            ))}
          </div>
        ) : null}
      </section>
      <section className="api-grid" aria-label="APIs">
        {state.status === 'loading' ? (
          <div role="status" aria-live="polite" className="api-grid-loading">
            {[0, 1, 2].map((i) => (
              <Card key={i} className="api-card">
                <div className="skeleton" style={{ height: 42, width: 160 }} aria-hidden />
                <div className="skeleton" style={{ height: 40 }} aria-hidden />
                <div className="skeleton" style={{ height: 14, width: 200 }} aria-hidden />
              </Card>
            ))}
            <span className="sr-only">Loading APIs</span>
          </div>
        ) : null}
        {state.status === 'error' ? (
          <ErrorState title="Could not load APIs" message={state.error.message} onRetry={retry} />
        ) : null}
        {items && items.length === 0 ? (
          <EmptyState title="No APIs yet">Published knowledge bases will show up here.</EmptyState>
        ) : null}
        {items && items.length > 0 && shown.length === 0 ? (
          <EmptyState title="No APIs match">Try another search or category.</EmptyState>
        ) : null}
        {shown.length > 0 ? (
          <ul className="api-list">
            {shown.map((a) => (
              <li key={a.id}>
                <ApiCard api={a} />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </>
  );
}
