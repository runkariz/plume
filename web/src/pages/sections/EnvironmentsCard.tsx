import { useCallback } from 'react';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip } from '@/components';

/**
 * Where the API lives (environments with their base URLs) and how it is versioned, from the package. It renders
 * nothing while loading, on error or when the package has no environments: it never shows an invented value.
 */
export function EnvironmentsCard({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getEnvironments(apiId, signal),
    [client, apiId],
  );
  const { state } = useAsync(load);
  if (state.status !== 'ready') return null;
  const { present, environments, versioning } = state.data;
  // the current version is usually also in the list of versions: say it once
  const others = (versioning?.versions ?? []).filter((v) => v !== versioning?.current);
  if (!present || (environments.length === 0 && !versioning)) return null;
  return (
    <Card className="pad" role="region" aria-label="Environments">
      <h2 className="h2-sm">Environments</h2>
      <ul className="sec-list">
        {environments.map((e, i) => (
          <li key={`${e.key ?? e.name ?? i}`} className="sec-item env-item">
            <div className="sec-main">
              <b>{e.name ?? e.key ?? 'environment'}</b> {e.kind ? <Chip>{e.kind}</Chip> : null}
              {e.isDefault ? <Chip tone="ok">default</Chip> : null}
              {e.baseUrl ? <div className="mono small env-url">{e.baseUrl}</div> : null}
            </div>
          </li>
        ))}
      </ul>
      {versioning && (versioning.current || versioning.versions?.length) ? (
        <p className="muted small" style={{ marginTop: 10 }}>
          API versions{versioning.scheme ? ` (${versioning.scheme})` : ''}:{' '}
          {versioning.current ? (
            <>
              current <span className="mono">{versioning.current}</span>
            </>
          ) : null}
          {others.length ? (
            <>
              {versioning.current ? ' · also ' : ''}
              <span className="mono">{others.join(', ')}</span>
            </>
          ) : null}
        </p>
      ) : null}
    </Card>
  );
}
