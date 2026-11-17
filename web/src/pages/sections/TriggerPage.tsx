import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type TriggerPayload } from '@/api/types';
import { Card, Chip, Crumbs, ErrorState, FieldTable, LoadingState, RawJson } from '@/components';
import { docHref } from '@/lib/docHref';
import { apiTitle } from '@/lib/names';
import { primitiveEntries } from './AuthSchemePage';

/**
 * What the event carries, as the package states it: the payload schema's fields (the same table as a model's) and
 * the sample, or a link to the connector model the payload is. Refs the server could not read are shown as text.
 */
function PayloadSection({ api, payload: p }: { api: string; payload: TriggerPayload }) {
  const hasSample = p.sample !== null && p.sample !== undefined;
  const unread = !p.model && p.fields.length === 0 && !hasSample;
  return (
    <>
      <Card className="pad doc-fields" role="region" aria-label="Payload">
        <h2 className="h2-sm">Payload</h2>
        {p.model ? (
          <p>
            The payload is the model{' '}
            <Link to={docHref(api, p.model.docId)}>{p.model.title ?? p.model.docId}</Link>.
          </p>
        ) : null}
        {unread ? (
          <p className="muted">
            The package names a payload, but Plume could not read it
            {p.schemaRef ? (
              <>
                {' '}
                (schema <span className="mono">{p.schemaRef}</span>)
              </>
            ) : null}
            {p.sampleRef ? (
              <>
                {' '}
                (sample <span className="mono">{p.sampleRef}</span>)
              </>
            ) : null}
            .
          </p>
        ) : null}
        {!p.model && !unread ? (
          <p className="faint small">
            {[
              p.schemaRef ? `Schema: ${p.schemaRef}` : '',
              p.sampleRef ? `Sample: ${p.sampleRef}` : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        ) : null}
      </Card>
      {!p.model && p.fields.length > 0 ? (
        <FieldTable title="Payload fields" fields={p.fields} />
      ) : null}
      {hasSample ? (
        <RawJson raw={p.sample} title="Sample payload, as in the package" label="Sample payload" />
      ) : null}
    </>
  );
}

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
  // the Payload section already says where the payload comes from
  if (d.payload) for (const k of ['payloadSchemaRef', 'sampleRef']) shown.add(k);
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

      {d.payload ? <PayloadSection api={apiId} payload={d.payload} /> : null}

      <RawJson raw={d.event} title="Event JSON, as in the package" label="Event JSON" open />
      <div style={{ height: 40 }} />
    </>
  );
}
