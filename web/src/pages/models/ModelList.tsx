import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { apiLabel } from '@/lib/names';
import { StaleChip } from './StaleChip';

/**
 * The canonical models that exist (optionally those using one API), newest first, each with a stale mark when
 * the docs it was built on have changed. It renders nothing while empty or if the list cannot be loaded: the
 * pages around it work without it.
 */
export function ModelList({ api, title = 'Existing models' }: { api?: string; title?: string }) {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listModels(api, signal), [client, api]);
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.items.length === 0) return null;
  return (
    <Card className="pad model-list" role="region" aria-label={title}>
      <h2 className="h2-sm">{title}</h2>
      <ul>
        {state.data.items.map((m) => (
          <li key={m.id}>
            <Link to={`/models/${m.id}`} className="model-list-link">
              <b>{m.name}</b>
            </Link>
            <span className="muted small">{m.apis.map((id) => apiLabel({ id })).join(' · ')}</span>
            <span className="faint small">{formatDate(m.generatedAt)}</span>
            {m.stale ? <StaleChip inputs={m.staleInputs} short /> : <Chip tone="ok">Current</Chip>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
