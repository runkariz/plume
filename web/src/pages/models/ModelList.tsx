import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ModelListItem, ModelVisibility } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { apiLabel } from '@/lib/names';
import { readOwnerKeys } from '@/lib/ownerKeys';
import { StaleChip } from './StaleChip';

function Rows({ items }: { items: ModelListItem[] }) {
  return (
    <ul>
      {items.map((m) => (
        <li key={m.id}>
          <Link to={`/models/${m.id}`} className="model-list-link">
            <b>{m.name}</b>
          </Link>
          <span className="muted small">{m.apis.map((id) => apiLabel({ id })).join(' · ')}</span>
          <span className="faint small">{formatDate(m.generatedAt)}</span>
          {m.versions && m.versions > 1 ? (
            <span className="faint small">
              v{m.version} of {m.versions}
            </span>
          ) : null}
          {m.official ? <Chip tone="ok">Official</Chip> : null}
          {m.visibility === 'unlisted' ? <Chip tone="info">Unlisted</Chip> : null}
          {m.visibility === 'unreleased' ? <Chip tone="warn">Unreleased</Chip> : null}
          {m.stale ? (
            <StaleChip inputs={m.staleInputs} short />
          ) : m.official === undefined ? (
            <Chip tone="ok">Current</Chip>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * The canonical models that exist (optionally those using one API), newest first. The public list holds released
 * (Official) models only; unlisted models never appear here. A model built on older docs has a stale mark. It
 * renders nothing while empty or if the list cannot be loaded: the pages around it work without it.
 */
export function ModelList({
  api,
  title = 'Official models',
  visibility,
}: {
  api?: string;
  title?: string;
  /** With a maintainer token only: "unreleased" lists the models waiting for review. */
  visibility?: ModelVisibility | 'all';
}) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.listModels(api, signal, visibility ? { visibility } : {}),
    [client, api, visibility],
  );
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.items.length === 0) return null;
  return (
    <Card className="pad model-list" role="region" aria-label={title}>
      <h2 className="h2-sm">{title}</h2>
      <Rows items={state.data.items} />
    </Card>
  );
}

/** The models waiting for review: only for a signed-in maintainer, nothing otherwise. */
export function UnreleasedModels() {
  const maintainer = useIsMaintainer();
  return maintainer ? <ModelList title="Waiting for review" visibility="unreleased" /> : null;
}

/**
 * "Your models": the unlisted models created with the owner keys this browser holds (the server lists them with
 * POST so the keys never reach a URL). Nothing is shown without keys or models.
 */
export function MyModels() {
  const client = useApiClient();
  const load = useCallback(
    async (signal: AbortSignal) => {
      const keys = readOwnerKeys();
      return keys.length ? client.listMyModels(keys, signal) : { items: [] };
    },
    [client],
  );
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.items.length === 0) return null;
  return (
    <Card className="pad model-list" role="region" aria-label="Your models">
      <h2 className="h2-sm">Your models</h2>
      <p className="muted small">
        Listed by the owner keys this browser holds: made here, or added by key. Only people with a
        model's link can open it.
      </p>
      <Rows items={state.data.items} />
    </Card>
  );
}
