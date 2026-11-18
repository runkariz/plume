import { useCallback, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type Environment } from '@/api/types';
import { Card, Chip, Crumbs, EndpointLinks, ErrorState, LoadingState, RawJson } from '@/components';
import { apiTitle } from '@/lib/names';
import { resolveServers, usesServers } from '@/lib/servers';

/** Setup steps come verbatim from the package: {order, text} in Shopify; strings or other shapes elsewhere. */
export function stepText(step: unknown): { order: number | null; text: string } {
  if (typeof step === 'string') return { order: null, text: step };
  if (step && typeof step === 'object') {
    const o = step as Record<string, unknown>;
    const text = typeof o.text === 'string' ? o.text : typeof o.title === 'string' ? o.title : '';
    const order = typeof o.order === 'number' ? o.order : null;
    if (text) return { order, text };
  }
  return { order: null, text: JSON.stringify(step) };
}

/** Primitive entries of a verbatim object (e.g. tokenLifetime) as label / value pairs. */
export function primitiveEntries(o: Record<string, unknown>): [string, string][] {
  return Object.entries(o).flatMap(([k, v]) =>
    typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
      ? [[k, String(v)] as [string, string]]
      : [],
  );
}

/** The URLs of an OAuth scheme the package states (verbatim in the scheme JSON), with the label shown for each. */
const URL_FIELDS: [string, string][] = [
  ['authUrl', 'Authorize URL'],
  ['accessTokenUrl', 'Token URL'],
  ['refreshTokenUrl', 'Refresh URL'],
];

/** A URL template that names a server ("{{app_env.servers.auth}}/token"), put into each environment that has it. */
function ResolvedUrls({
  label,
  template,
  environments,
}: {
  label: string;
  template: string;
  environments: Environment[];
}) {
  if (!usesServers(template)) return null;
  const rows = environments.flatMap((e) => {
    const url = resolveServers(template, e.servers);
    return url ? [{ name: e.name ?? e.key ?? 'environment', url }] : [];
  });
  if (rows.length === 0) return null;
  return (
    <ul className="resolved-urls" aria-label={`${label} per environment`}>
      {rows.map((r, i) => (
        <li key={`${r.name}-${i}`}>
          <span className="muted">{r.name}:</span> <span className="mono">{r.url}</span>
        </li>
      ))}
    </ul>
  );
}

/** One auth scheme: how it works, its scopes, the variables it needs, the setup steps, all from the package. */
export function AuthSchemePage() {
  const { apiId = '', schemeId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getAuthScheme(apiId, schemeId, signal),
    [client, apiId, schemeId],
  );
  const { state, retry } = useAsync(load);
  const loadApi = useCallback(
    (signal: AbortSignal) => client.getApi(apiId, signal),
    [client, apiId],
  );
  const { state: apiState } = useAsync(loadApi);
  const apiName = apiState.status === 'ready' ? apiTitle(apiState.data) : apiId;
  // the environments resolve the server placeholders of the token/authorize URLs; without them the templates stand alone
  const loadEnv = useCallback(
    (signal: AbortSignal) => client.getEnvironments(apiId, signal),
    [client, apiId],
  );
  const { state: envState } = useAsync(loadEnv);
  const environments = envState.status === 'ready' ? envState.data.environments : [];
  const [scopeQuery, setScopeQuery] = useState('');

  const data = state.status === 'ready' ? state.data : null;
  const q = scopeQuery.trim().toLowerCase();
  const scopes = useMemo(
    () =>
      (data?.scopes ?? []).filter(
        (s) => !q || `${s.scope ?? ''} ${s.description ?? ''}`.toLowerCase().includes(q),
      ),
    [data, q],
  );

  const crumbs = (last: string) => [
    { label: 'APIs', to: '/' },
    { label: apiName, to: `/apis/${apiId}` },
    { label: 'Authentication', to: `/apis/${apiId}?section=auth` },
    { label: last },
  ];

  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs('Scheme')} />
        <LoadingState label="Loading the authentication scheme" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs('Scheme')} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Authentication scheme not found'
              : 'Could not load this scheme'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );

  const d = state.data;
  const facts: [string, string | null][] = [
    ['Type', d.type],
    ['Grant type', d.grantType],
    ['Header', d.headerName],
    ['Query parameter', d.queryParam],
    ['Test URL', d.testUrl],
  ];
  const urlFacts = URL_FIELDS.flatMap(([key, label]) => {
    const v = d.scheme?.[key];
    return typeof v === 'string' && v ? [{ key, label, template: v }] : [];
  });
  const withEndpoints = d.scopes.some((s) => (s.endpoints?.length ?? 0) > 0);
  const steps = (d.setupSteps ?? []).map(stepText);
  const lifetime = d.tokenLifetime ? primitiveEntries(d.tokenLifetime) : [];

  return (
    <>
      <Crumbs items={crumbs(d.name)} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{d.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            {d.type ? <Chip tone="info">{d.type}</Chip> : null}
            {d.grantType ? <Chip>{d.grantType}</Chip> : null}
            <span className="faint small mono">{d.docId}</span>
          </div>
        </div>
        <Link className="btn" to={`/apis/${apiId}?section=auth`}>
          Back to {apiName}
        </Link>
      </div>

      <Card className="pad doc-fields" role="region" aria-label="How it works">
        <h2 className="h2-sm">How it works</h2>
        <dl className="facts">
          {facts
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k} className="fact">
                <dt className="muted">{k}</dt>
                <dd className="mono">{v}</dd>
              </div>
            ))}
          {urlFacts.map((u) => (
            <div key={u.key} className="fact fact-url">
              <dt className="muted">{u.label}</dt>
              <dd>
                <span className="mono">{u.template}</span>
                <ResolvedUrls label={u.label} template={u.template} environments={environments} />
              </dd>
            </div>
          ))}
          {lifetime.map(([k, v]) => (
            <div key={`tl-${k}`} className="fact">
              <dt className="muted">Token lifetime: {k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {steps.length ? (
        <Card className="pad doc-fields" role="region" aria-label="Setup steps">
          <h2 className="h2-sm">Setup steps</h2>
          <ol className="setup-steps">
            {steps.map((s, i) => (
              <li key={i}>{s.text}</li>
            ))}
          </ol>
        </Card>
      ) : null}

      {d.variables.length ? (
        <Card className="pad doc-fields" role="region" aria-label="Variables">
          <h2 className="h2-sm">
            Variables <span className="faint small">({d.variables.length})</span>
          </h2>
          <table className="ev-fields">
            <caption className="sr-only">Variables this scheme needs</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
                <th scope="col">Description</th>
              </tr>
            </thead>
            <tbody>
              {d.variables.map((v) => (
                <tr key={v.name}>
                  <th scope="row" className="mono doc-field-name">
                    {v.name}
                    {v.required ? <span className="chip acc ev-req">required</span> : null}
                  </th>
                  <td className="mono">{v.type ?? '–'}</td>
                  <td className="muted">{v.description ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}

      {d.scopes.length ? (
        <Card className="pad doc-fields" role="region" aria-label="Scopes">
          <h2 className="h2-sm">
            Scopes <span className="faint small">({d.scopes.length})</span>
          </h2>
          {d.scopes.length > 12 ? (
            <div className="searchbar" style={{ marginBottom: 8 }}>
              <input
                type="search"
                aria-label="Filter scopes"
                placeholder="Filter scopes by name or description"
                value={scopeQuery}
                onChange={(e) => setScopeQuery(e.target.value)}
              />
            </div>
          ) : null}
          <p className="faint small" aria-live="polite">
            {scopes.length} of {d.scopes.length} scopes
          </p>
          <table className="ev-fields">
            <caption className="sr-only">Scopes of this scheme</caption>
            <thead>
              <tr>
                <th scope="col">Scope</th>
                <th scope="col">Description</th>
                {withEndpoints ? <th scope="col">Endpoints that need it</th> : null}
              </tr>
            </thead>
            <tbody>
              {scopes.map((s, i) => (
                <tr key={`${s.scope}-${i}`}>
                  <th scope="row" className="mono doc-field-name">
                    {s.scope}
                  </th>
                  <td className="muted">{s.description ?? ''}</td>
                  {withEndpoints ? (
                    <td className="scope-endpoints">
                      <EndpointLinks
                        api={apiId}
                        ids={s.endpoints}
                        label={`Endpoints that need ${s.scope ?? 'this scope'}`}
                        collapseAt={3}
                      />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}

      <RawJson raw={d.scheme} title="Scheme JSON, as in the package" label="Scheme JSON" />
      {d.variablesSchema ? (
        <RawJson
          raw={d.variablesSchema}
          title="Variables JSON Schema, as in the package"
          label="Variables JSON Schema"
        />
      ) : null}
      <div style={{ height: 40 }} />
    </>
  );
}
