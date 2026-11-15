import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ModelVisibility, SetListItem } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { apiLabel } from '@/lib/names';
import { readOwnerKeys } from '@/lib/ownerKeys';

function Rows({ items }: { items: SetListItem[] }) {
  return (
    <ul>
      {items.map((s) => (
        <li key={s.id}>
          <Link to={`/model-sets/${s.id}`} className="model-list-link">
            <b>{s.name}</b>
          </Link>
          <span className="muted small">{s.apis.map((id) => apiLabel({ id })).join(' · ')}</span>
          <span className="faint small">
            {s.members.length} models · {s.relations} relations
          </span>
          <span className="faint small">{formatDate(s.generatedAt)}</span>
          {s.versions && s.versions > 1 ? (
            <span className="faint small">
              v{s.version} of {s.versions}
            </span>
          ) : null}
          {s.official ? <Chip tone="ok">Official</Chip> : null}
          {s.visibility === 'unlisted' ? <Chip tone="info">Unlisted</Chip> : null}
          {s.visibility === 'unreleased' ? <Chip tone="warn">Unreleased</Chip> : null}
          {s.undecided ? <Chip tone="warn">{s.undecided} to decide</Chip> : null}
          {s.stale ? <Chip tone="warn">Stale</Chip> : null}
        </li>
      ))}
    </ul>
  );
}

/** A list of model sets, or nothing while it is empty or cannot be loaded (the page around it works without it). */
function SetList({
  title,
  intro,
  load,
}: {
  title: string;
  intro?: string;
  load: (signal: AbortSignal) => Promise<{ items: SetListItem[] }>;
}) {
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.items.length === 0) return null;
  return (
    <Card className="pad model-list" role="region" aria-label={title}>
      <h2 className="h2-sm">{title}</h2>
      {intro ? <p className="muted small">{intro}</p> : null}
      <Rows items={state.data.items} />
    </Card>
  );
}

/** The released model sets (the latest version of each). */
export function OfficialSets() {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listModelSets({}, signal), [client]);
  return <SetList title="Official model sets" load={load} />;
}

/** The sets waiting for review: only for a signed-in maintainer. */
export function UnreleasedSets() {
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const load = useCallback(
    (signal: AbortSignal) =>
      maintainer
        ? client.listModelSets({ visibility: 'unreleased' satisfies ModelVisibility }, signal)
        : Promise.resolve({ items: [] }),
    [client, maintainer],
  );
  return <SetList title="Sets waiting for review" load={load} />;
}

/** The sets made in this browser (owner keys); POST so the keys never reach a URL. */
export function MySets() {
  const client = useApiClient();
  const load = useCallback(
    async (signal: AbortSignal) => {
      const keys = readOwnerKeys();
      return keys.length ? client.listMyModelSets(keys, signal) : { items: [] };
    },
    [client],
  );
  return (
    <SetList
      title="Your model sets"
      intro="Listed by the owner keys this browser holds: made here, or added by key. Only people with a set's link can open it."
      load={load}
    />
  );
}
