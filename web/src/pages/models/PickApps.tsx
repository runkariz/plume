import { useCallback, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ApiSummary } from '@/api/types';
import { ApiAvatar, Button, EmptyState, ErrorState, LoadingState } from '@/components';
import { CheckIcon } from '@/icons';

function PickCard({
  api,
  checked,
  onToggle,
}: {
  api: ApiSummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className={`card pick-card${checked ? ' on' : ''}`}>
      <input type="checkbox" className="sr-only" checked={checked} onChange={onToggle} />
      <span className="pick-box" aria-hidden>
        {checked ? <CheckIcon width={14} height={14} /> : null}
      </span>
      <span className="api-top">
        <ApiAvatar text={api.logo.text} color={api.logo.color} size={42} />
        <span>
          <span className="api-name">{api.name}</span>
          <br />
          <span className="faint small">{api.category}</span>
        </span>
      </span>
      <span className="api-desc muted">{api.summary}</span>
      <span className="api-stats muted">
        <span>
          <b>{api.endpoints}</b> endpoints
        </span>
        <span>
          <b>{api.models}</b> models
        </span>
        <span>
          <b>{api.guides}</b> guides
        </span>
      </span>
    </label>
  );
}

export function PickApps() {
  const client = useApiClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const load = useCallback((signal: AbortSignal) => client.listModelCandidates(signal), [client]);
  const { state, retry } = useAsync(load);
  const [selected, setSelected] = useState<string[]>(() =>
    (params.get('apis') ?? '').split(',').filter(Boolean),
  );
  const [category, setCategory] = useState<string | null>(null);

  const items = state.status === 'ready' ? state.data.items : null;
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of items ?? []) counts.set(a.category, (counts.get(a.category) ?? 0) + 1);
    return [...counts.entries()];
  }, [items]);
  const shown = (items ?? []).filter((a) => !category || a.category === category);
  const chosen = selected
    .map((id) => items?.find((a) => a.id === id))
    .filter((a): a is ApiSummary => Boolean(a));

  function toggle(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  return (
    <>
      <section className="hero pick-hero">
        <div className="eyebrow">Create a canonical model</div>
        <h1>
          Pick the APIs you
          <br />
          want to <em>unify.</em>
        </h1>
        <p className="lead" style={{ marginTop: 20 }}>
          Select two or more. Plume looks across them and suggests the models you can build.
        </p>
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
                {name} · {count}
              </button>
            ))}
          </div>
        ) : null}
      </section>
      <section className="api-grid pick-grid" aria-label="APIs to unify">
        {state.status === 'loading' ? <LoadingState label="Loading APIs" /> : null}
        {state.status === 'error' ? (
          <ErrorState title="Could not load APIs" message={state.error.message} onRetry={retry} />
        ) : null}
        {items && items.length === 0 ? (
          <EmptyState title="No APIs to model yet">
            Publish at least two APIs, then come back to unify them.
          </EmptyState>
        ) : null}
        {shown.length > 0 ? (
          <ul className="api-list">
            {shown.map((a) => (
              <li key={a.id}>
                <PickCard api={a} checked={selected.includes(a.id)} onToggle={() => toggle(a.id)} />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      {selected.length > 0 ? (
        <div className="selbar" role="region" aria-label="Selected APIs">
          <b aria-live="polite">{selected.length} selected</b>
          <ul className="selbar-chips">
            {chosen.map((a) => (
              <li key={a.id} className="selbar-chip">
                <ApiAvatar text={a.logo.text} color={a.logo.color} size={22} />
                {a.name.split(' ')[0]}
              </li>
            ))}
          </ul>
          <button type="button" className="selbar-clear" onClick={() => setSelected([])}>
            Clear
          </button>
          <Button
            variant="primary"
            size="lg"
            disabled={selected.length < 2}
            onClick={() => navigate(`/models/suggest?apis=${selected.join(',')}`)}
          >
            Suggest models →
          </Button>
          {selected.length < 2 ? <span className="sr-only">Select at least two APIs</span> : null}
        </div>
      ) : null}
      <p className="sr-only">
        <Link to="/">Back to the API list</Link>
      </p>
    </>
  );
}
