import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError } from '@/api/types';
import { Card, Chip, Crumbs, ErrorState, LoadingState, RawJson } from '@/components';
import { apiTitle } from '@/lib/names';
import { primitiveEntries } from './AuthSchemePage';

/** One trigger / webhook event: what it is and when it fires (from the package), with the event JSON verbatim. */
export function TriggerPage() {
  const { apiId = '', triggerKey = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getTrigger(apiId, triggerKey, signal),
    [client, apiId, triggerKey],
  );
  const { state, retry } = useAsync(load);
  const loadApi = useCallback(
    (signal: AbortSignal) => client.getApi(apiId, signal),
    [client, apiId],
  );
  const { state: apiState } = useAsync(loadApi);
  const apiName = apiState.status === 'ready' ? apiTitle(apiState.data) : apiId;

  const crumbs = (last: string) => [
    { label: 'APIs', to: '/' },
    { label: apiName, to: `/apis/${apiId}` },
    { label: 'Triggers', to: `/apis/${apiId}?section=triggers` },
    { label: last },
  ];

  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs('Event')} />
        <LoadingState label="Loading the event" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs('Event')} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Event not found'
              : 'Could not load this event'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );

  const d = state.data;
  // plain facts the event carries, besides what the header already shows
  const shown = new Set(['key', 'title', 'description', 'resource', 'delivery']);
  const extra = primitiveEntries(d.event).filter(([k]) => !shown.has(k));

  return (
    <>
      <Crumbs items={crumbs(d.title)} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm mono">{d.title}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            {d.resource ? <Chip>{d.resource}</Chip> : null}
            {d.delivery ? <Chip tone="info">{d.delivery}</Chip> : null}
            <span className="faint small mono">{d.docId}</span>
          </div>
        </div>
        <div className="row">
          <Link className="btn" to={`/apis/${apiId}?section=triggers`}>
            Back to {apiName}
          </Link>
          {d.sourceUrl ? (
            <a className="btn" href={d.sourceUrl} target="_blank" rel="noreferrer">
              Open the vendor page
            </a>
          ) : (
            <span className="faint small">No vendor link in the package</span>
          )}
        </div>
      </div>

      <Card className="pad doc-fields" role="region" aria-label="Event">
        <h2 className="h2-sm">What it is</h2>
        {d.description ? (
          <p>{d.description}</p>
        ) : (
          <p className="muted">The package gives no description for this event.</p>
        )}
        {extra.length ? (
          <dl className="facts">
            {extra.map(([k, v]) => (
              <div key={k} className="fact">
                <dt className="muted">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </Card>

      <RawJson raw={d.event} title="Event JSON, as in the package" label="Event JSON" open />
      <div style={{ height: 40 }} />
    </>
  );
}
