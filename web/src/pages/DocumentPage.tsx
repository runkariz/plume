import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type DocumentOut, type HttpMethod } from '@/api/types';
import {
  Card,
  Chip,
  Crumbs,
  EndpointRateLimitCard,
  EndpointLinks,
  ErrorState,
  GuideLinks,
  LoadingState,
  MethodBadge,
  RawJson,
} from '@/components';
import { constraintParts } from '@/lib/constraints';
import { breakable } from '@/lib/breakable';
import { operationOf, schemeIdOf, shownPath } from '@/lib/docHref';
import { formatDate, shortBuild } from '@/lib/format';
import { apiTitle } from '@/lib/names';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

/** The order and the names of the parameter groups of an endpoint. */
const GROUPS: { location: string; title: string }[] = [
  { location: 'path', title: 'Path parameters' },
  { location: 'query', title: 'Query parameters' },
  { location: 'header', title: 'Headers' },
  { location: 'cookie', title: 'Cookies' },
  { location: 'body', title: 'Request body' },
  { location: 'response', title: 'Response fields' },
  { location: 'model', title: 'Fields' },
];

type Field = DocumentOut['fields'][number];

/** A verbatim value from the package, as text (objects are not guessed at). */
function text(v: unknown): string {
  return typeof v === 'string' || typeof v === 'number' ? String(v) : '';
}

/** What the package says about the allowed values of a field, as small plain-text chips. */
function Constraints({ value }: { value: Field['constraints'] }) {
  const parts = constraintParts(value);
  if (parts.length === 0) return null;
  return (
    <ul className="constraints" aria-label="Constraints">
      {parts.map((p) => (
        <li key={p.label}>
          <span className="faint">{p.label}</span> <span className="mono">{p.value}</span>
        </li>
      ))}
    </ul>
  );
}

function FieldTable({ title, fields }: { title: string; fields: Field[] }) {
  return (
    <Card className="pad doc-fields" role="region" aria-label={title}>
      <h2 className="h2-sm">
        {title} <span className="faint small">({fields.length})</span>
      </h2>
      <table className="ev-fields">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Type</th>
            <th scope="col">Description</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => (
            <tr key={`${f.name}-${i}`}>
              <th scope="row" className="mono doc-field-name">
                {f.name}
                {f.required ? <span className="chip acc ev-req">required</span> : null}
              </th>
              <td className="mono">{f.type ?? '–'}</td>
              <td className="muted">
                {f.description ?? ''}
                <Constraints value={f.constraints} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/**
 * One stored document: an endpoint, a model, a guide, an auth scheme or a trigger. Citations and Browse rows
 * point here. Everything shown comes from the API; vendor text is untrusted and rendered as plain text.
 */
export function DocumentPage() {
  const { apiId = '', docId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getDocument(apiId, docId, signal),
    [client, apiId, docId],
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
    { label: last },
  ];

  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs('Document')} />
        <LoadingState label="Loading the document" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs('Document')} />
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
  const groups = GROUPS.map((g) => ({
    ...g,
    fields: d.fields.filter((f) => f.location === g.location),
  })).filter((g) => g.fields.length > 0);
  const known = new Set(GROUPS.map((g) => g.location));
  const other = d.fields.filter((f) => !known.has(f.location));
  const perScheme = (d.requiredScopes ?? []).filter((r) => r.scopes.length > 0);
  const isGuide = d.kind === 'guide' || d.kind === 'app';
  const hasStructure = groups.length > 0 || other.length > 0;

  return (
    <>
      <Crumbs items={crumbs(d.title)} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{d.title}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <Chip>{d.kind}</Chip>
            {d.method && METHODS.includes(d.method) ? (
              <MethodBadge method={d.method as HttpMethod} />
            ) : null}
            {shownPath(d) ? (
              <span
                className="mono doc-path"
                title={
                  d.realPath && d.path && d.realPath !== d.path
                    ? `Package path: ${d.path}`
                    : undefined
                }
              >
                {breakable(shownPath(d) ?? '')}
              </span>
            ) : null}
            {operationOf(d.id, d.method, d.path) ? (
              <span className="faint small mono">· {operationOf(d.id, d.method, d.path)}</span>
            ) : null}
            {d.resource ? <Chip>{d.resource}</Chip> : null}
            {d.deprecated ? <Chip tone="warn">deprecated</Chip> : null}
            {!d.complete ? <Chip tone="warn">partial schema</Chip> : null}
            {(d.tags ?? []).map((t) => (
              <Chip key={t} tone="info">
                {t}
              </Chip>
            ))}
          </div>
          <p className="faint small" style={{ marginTop: 8 }}>
            <span className="mono">{d.id}</span> · build{' '}
            <span className="mono" title={d.build}>
              {shortBuild(d.build)}
            </span>{' '}
            · docs as of {formatDate(d.docsAsOf)}
          </p>
        </div>
        <div className="row">
          <Link className="btn" to={`/apis/${apiId}`}>
            Back to {apiName}
          </Link>
          {d.sourceUrl ? (
            <a
              className="btn"
              href={`${d.sourceUrl}${d.anchor ?? ''}`}
              target="_blank"
              rel="noreferrer"
            >
              Open the vendor page
            </a>
          ) : (
            <span className="faint small">No vendor link in the package</span>
          )}
        </div>
      </div>

      <EndpointRateLimitCard limit={d.rateLimit} />

      {perScheme.length ? (
        <Card className="pad doc-scopes" role="region" aria-label="Required scopes">
          <h2 className="h2-sm">Required scopes</h2>
          <div className="scheme-scopes">
            {perScheme.map((r, i) => (
              <div key={`${r.authId ?? 'any'}-${i}`} className="scheme-row">
                {r.authId ? (
                  <Link
                    className="mono small"
                    to={`/apis/${apiId}/auth/${encodeURIComponent(schemeIdOf(r.authId))}`}
                  >
                    {r.authId}
                  </Link>
                ) : (
                  <span className="faint small" title="The package does not name the scheme">
                    Any scheme
                  </span>
                )}
                <span className="row">
                  {r.scopes.map((s) => (
                    <Chip key={s}>{s}</Chip>
                  ))}
                </span>
              </div>
            ))}
          </div>
        </Card>
      ) : d.scopes.length ? (
        <Card className="pad doc-scopes" role="region" aria-label="Scopes">
          <h2 className="h2-sm">{d.kind === 'auth' ? 'Scopes' : 'Required scopes'}</h2>
          <div className="row">
            {d.scopes.map((s) => (
              <Chip key={s}>{s}</Chip>
            ))}
          </div>
        </Card>
      ) : null}

      {d.guides?.length ? (
        <Card className="pad" role="region" aria-label="Related guides">
          <h2 className="h2-sm">
            Related guides <span className="faint small">({d.guides.length})</span>
          </h2>
          <GuideLinks api={apiId} ids={d.guides} />
        </Card>
      ) : null}

      {d.linkedEndpoints?.length ? (
        <Card className="pad" role="region" aria-label="About these endpoints">
          <h2 className="h2-sm">
            About these endpoints <span className="faint small">({d.linkedEndpoints.length})</span>
          </h2>
          <EndpointLinks
            api={apiId}
            ids={d.linkedEndpoints}
            label="Endpoints this guide is about"
          />
        </Card>
      ) : null}

      {d.responses?.length ? (
        <Card className="pad" role="region" aria-label="Responses">
          <h2 className="h2-sm">Responses</h2>
          <ul className="doc-responses">
            {d.responses.map((r, i) => {
              const status = text(r.statusCode ?? r.status);
              return (
                <li key={`${status}-${i}`}>
                  {status ? (
                    <Chip tone={status.startsWith('2') ? 'ok' : 'neutral'}>{status}</Chip>
                  ) : null}{' '}
                  {text(r.contentType) ? (
                    <span className="mono small">{text(r.contentType)}</span>
                  ) : null}{' '}
                  <span className="muted">{text(r.description ?? r.meaning)}</span>
                  {text(r.contentContractRef) ? (
                    <span className="faint small mono"> {text(r.contentContractRef)}</span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </Card>
      ) : null}

      {d.errors?.length ? (
        <Card className="pad" role="region" aria-label="Errors">
          <h2 className="h2-sm">Errors</h2>
          <ul className="doc-responses">
            {d.errors.map((e, i) => (
              <li key={`${text(e.status)}-${i}`}>
                {text(e.status ?? e.statusCode) ? (
                  <Chip tone="bad">{text(e.status ?? e.statusCode)}</Chip>
                ) : null}{' '}
                <span className="muted">{text(e.meaning ?? e.description)}</span>
                {e.retryable === true ? <Chip tone="warn">retryable</Chip> : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {groups.map((g) => (
        <FieldTable key={g.location} title={g.title} fields={g.fields} />
      ))}
      {other.length ? <FieldTable title="Other fields" fields={other} /> : null}
      {!hasStructure && !isGuide && d.kind !== 'auth' ? (
        <Card className="pad">
          <p className="muted">The package documents no fields for this {d.kind}.</p>
        </Card>
      ) : null}

      <Card className="pad doc-text-card">
        {hasStructure && !isGuide ? (
          <details>
            <summary>
              <b>Full text</b>
            </summary>
            <pre className="doc-text">{d.text}</pre>
          </details>
        ) : (
          <>
            <h2 className="h2-sm">Text</h2>
            <pre className="doc-text">{d.text}</pre>
          </>
        )}
      </Card>

      {d.raw !== undefined && d.raw !== null ? (
        <RawJson raw={d.raw} truncated={d.rawTruncated} />
      ) : null}
      <div style={{ height: 40 }} />
    </>
  );
}
