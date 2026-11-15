import { useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError } from '@/api/types';
import { Card, Chip, Crumbs, ErrorState, LoadingState, MethodBadge } from '@/components';
import type { HttpMethod } from '@/api/types';
import { breakable } from '@/lib/breakable';
import { formatDate, shortBuild } from '@/lib/format';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

/** One stored document: what a model citation points at. Everything here is vendor text: shown as plain text. */
export function DocumentPage() {
  const { apiId = '', docId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getDocument(apiId, docId, signal),
    [client, apiId, docId],
  );
  const { state, retry } = useAsync(load);
  const crumbs = [
    { label: 'APIs', to: '/' },
    { label: apiId, to: `/apis/${apiId}` },
    { label: 'Document' },
  ];

  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the document" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Document not found'
              : 'Could not load this document'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );

  const d = state.data;
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{d.title}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <Chip>{d.kind}</Chip>
            {d.method && METHODS.includes(d.method) ? (
              <MethodBadge method={d.method as HttpMethod} />
            ) : null}
            {d.path ? <span className="mono">{breakable(d.path)}</span> : null}
            {d.deprecated ? <Chip tone="warn">deprecated</Chip> : null}
            {!d.complete ? <Chip tone="warn">partial schema</Chip> : null}
          </div>
          <p className="faint small" style={{ marginTop: 8 }}>
            <span className="mono">{d.id}</span> · build{' '}
            <span className="mono" title={d.build}>
              {shortBuild(d.build)}
            </span>{' '}
            · docs as of {formatDate(d.docsAsOf)}
          </p>
        </div>
        {d.sourceUrl ? (
          <a
            className="btn"
            href={`${d.sourceUrl}${d.anchor ?? ''}`}
            target="_blank"
            rel="noreferrer"
          >
            Open the vendor page
          </a>
        ) : null}
      </div>
      <div className="cols doc-cols">
        <Card className="pad">
          <h2 className="h2-sm">Text</h2>
          <pre className="doc-text">{d.text}</pre>
        </Card>
        <div className="stack">
          <Card className="pad">
            <h2 className="h2-sm">Fields</h2>
            {d.fields.length === 0 ? (
              <p className="muted">No documented fields.</p>
            ) : (
              <table className="ev-fields">
                <caption className="sr-only">Fields of {d.title}</caption>
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Where</th>
                    <th scope="col">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {d.fields.map((f, i) => (
                    <tr key={`${f.name}-${f.location}-${i}`}>
                      <td className="mono">
                        {f.name}
                        {f.required ? <span className="chip acc ev-req">required</span> : null}
                        {f.description ? <div className="muted small">{f.description}</div> : null}
                      </td>
                      <td>{f.location}</td>
                      <td className="mono">{f.type ?? '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          {d.scopes.length ? (
            <Card className="pad">
              <h2 className="h2-sm">Scopes</h2>
              <div className="row">
                {d.scopes.map((s) => (
                  <Chip key={s}>{s}</Chip>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}
