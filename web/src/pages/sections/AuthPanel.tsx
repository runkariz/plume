import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip, EmptyState, ErrorState, LoadingState, Notices } from '@/components';
import { headerLine } from './HeaderSource';

/** The auth schemes of the package (type, grant, header or query parameter, scopes, variables), one card each. */
export function AuthPanel({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.getAuth(apiId, signal), [client, apiId]);
  const { state, retry } = useAsync(load);
  return (
    <Card className="pad" role="region" aria-label="Authentication">
      <h2 className="h2-sm">Authentication</h2>
      {state.status === 'loading' ? <LoadingState label="Loading authentication" /> : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not load authentication"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {state.status === 'ready' ? <Notices items={state.data.notices} api={apiId} /> : null}
      {state.status === 'ready' && (!state.data.present || state.data.schemes.length === 0) ? (
        <EmptyState title="Not in this package">
          {state.data.note
            ? `The package has no authentication section (${state.data.note}).`
            : 'The package does not document how to authenticate.'}
        </EmptyState>
      ) : null}
      {state.status === 'ready' && state.data.present && state.data.schemes.length > 0 ? (
        <ul className="sec-list">
          {state.data.schemes.map((s) => (
            <li key={s.id} className="sec-item">
              <div className="sec-main">
                <Link
                  className="sec-link"
                  to={`/apis/${encodeURIComponent(apiId)}/auth/${encodeURIComponent(s.id)}`}
                >
                  {s.name}
                </Link>
                <div className="row" style={{ gap: 8, marginTop: 6 }}>
                  {s.type ? <Chip tone="info">{s.type}</Chip> : null}
                  {s.grantType ? <Chip>{s.grantType}</Chip> : null}
                  {s.headerName ? (
                    <span className="mono small">{headerLine(s) ?? `header ${s.headerName}`}</span>
                  ) : null}
                  {s.queryParam ? <span className="mono small">query {s.queryParam}</span> : null}
                </div>
                {s.headerNote?.trim() ? (
                  <p className="faint small header-note">{s.headerNote.trim()}</p>
                ) : null}
              </div>
              <div className="faint small sec-counts">
                {s.scopes} scope{s.scopes === 1 ? '' : 's'} · {s.variables} variable
                {s.variables === 1 ? '' : 's'}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
