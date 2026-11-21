import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { RemoveApiResult } from '@/api/types';
import { Card, Crumbs, EmptyState, ErrorState, LoadingState, Logo } from '@/components';
import { formatDate } from '@/lib/format';
import { DisplayNameEditor } from './DisplayNameEditor';
import { ReleaseReviewLink } from './release/BuildsPage';
import { RemoveApi, RemovedNotice } from './RemoveApi';

export function MaintainerHome() {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state, retry } = useAsync(load);
  const [removing, setRemoving] = useState<string | null>(null);
  const [removed, setRemoved] = useState<RemoveApiResult | null>(null);
  return (
    <>
      <Crumbs items={[{ label: 'Maintainer' }]} />
      <div className="titlerow">
        <h1 className="h1-sm">Maintainer</h1>
        <div className="row">
          <Link className="btn" to="/maintainer/reports">
            Reported questions
          </Link>
          <Link className="btn primary" to="/maintainer/apis/new/update">
            Add an API
          </Link>
        </div>
      </div>
      {removed ? <RemovedNotice result={removed} onDismiss={() => setRemoved(null)} /> : null}
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
              <li key={a.id} className="m-row m-row-wrap">
                <Logo text={a.logo.text} color={a.logo.color} url={a.logo.url} size={36} />
                <div className="m-main">
                  <b>{a.name}</b>
                  <DisplayNameEditor api={a} onChanged={retry} />
                  <span className="muted small">
                    {a.docsAsOf ? `Docs as of ${formatDate(a.docsAsOf)}` : 'No docs published yet'}
                  </span>
                </div>
                <ReleaseReviewLink api={a.id} />
                <Link className="btn" to={`/apis/${a.id}/try`}>
                  Try it
                </Link>
                <Link className="btn primary" to={`/maintainer/apis/${a.id}/update`}>
                  Update knowledge
                </Link>
                <button
                  type="button"
                  className="btn"
                  aria-label={`Remove ${a.name}`}
                  aria-expanded={removing === a.id}
                  onClick={() => setRemoving(removing === a.id ? null : a.id)}
                >
                  Remove…
                </button>
                {removing === a.id ? (
                  <div className="m-row-extra">
                    <RemoveApi
                      api={a}
                      onClose={() => setRemoving(null)}
                      onRemoved={(r) => {
                        setRemoving(null);
                        setRemoved(r);
                        retry();
                      }}
                    />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
