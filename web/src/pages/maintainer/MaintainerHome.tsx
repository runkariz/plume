import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Crumbs, EmptyState, ErrorState, LoadingState, Logo } from '@/components';
import { formatDate } from '@/lib/format';

export function MaintainerHome() {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state, retry } = useAsync(load);
  return (
    <>
      <Crumbs items={[{ label: 'Maintainer' }]} />
      <div className="titlerow">
        <h1 className="h1-sm">Maintainer</h1>
        <Link className="btn primary" to="/maintainer/apis/new/update">
          Add an API
        </Link>
      </div>
      {state.status === 'loading' ? <LoadingState label="Loading APIs" /> : null}
      {state.status === 'error' ? (
        <ErrorState title="Could not load APIs" message={state.error.message} onRetry={retry} />
      ) : null}
      {state.status === 'ready' && state.data.items.length === 0 ? (
        <EmptyState title="No APIs yet">Add an API by uploading a package.</EmptyState>
      ) : null}
      {state.status === 'ready' && state.data.items.length > 0 ? (
        <Card className="pad">
          <ul className="m-list">
            {state.data.items.map((a) => (
              <li key={a.id} className="m-row">
                <Logo text={a.logo.text} color={a.logo.color} size={36} />
                <div className="m-main">
                  <b>{a.name}</b>
                  <span className="muted small">Docs as of {formatDate(a.docsAsOf)}</span>
                </div>
                <Link className="btn" to={`/apis/${a.id}/try`}>
                  Try it
                </Link>
                <Link className="btn primary" to={`/maintainer/apis/${a.id}/update`}>
                  Update knowledge
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
