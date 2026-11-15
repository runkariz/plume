import { useCallback, useState } from 'react';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ApiRef, EvidencePage } from '@/api/types';
import { Button, Chip } from '@/components';
import { shortBuild } from '@/lib/format';

type Doc = EvidencePage['documents'][number];
interface Loaded {
  docs: Doc[];
  returned: number;
  total: number;
  next: number | null;
  missing: string[];
}
type ApiState =
  | { status: 'idle' }
  | { status: 'loading'; loaded?: Loaded }
  | { status: 'error'; message: string; loaded?: Loaded }
  | { status: 'ready'; loaded: Loaded };

/** Pages can split one document across two pages: join its fields instead of repeating the document. */
function mergePage(prev: Loaded | undefined, page: EvidencePage): Loaded {
  const docs = prev ? prev.docs.map((d) => ({ ...d, fields: [...d.fields] })) : [];
  for (const d of page.documents) {
    const hit = docs.find((x) => x.doc_id === d.doc_id);
    if (hit) hit.fields.push(...d.fields);
    else docs.push({ ...d, fields: [...d.fields] });
  }
  return {
    docs,
    returned: (prev?.returned ?? 0) + page.returned,
    total: page.total_fields,
    next: page.next_cursor,
    missing: [...new Set([...(prev?.missing ?? []), ...page.missing_doc_ids])],
  };
}

function Fields({ docs }: { docs: Doc[] }) {
  return (
    <div className="ev-docs">
      {docs.map((d) => (
        <div key={d.doc_id} className="ev-doc">
          <div className="ev-doc-head">
            <b>{d.title}</b> <span className="mono faint small">{d.doc_id}</span>
            {!d.complete ? <Chip tone="warn">partial schema</Chip> : null}
          </div>
          {d.fields.length === 0 ? (
            <p className="muted small">No documented fields.</p>
          ) : (
            <table className="ev-fields">
              <caption className="sr-only">Fields of {d.title}</caption>
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">Type</th>
                  <th scope="col">Description</th>
                </tr>
              </thead>
              <tbody>
                {d.fields.map((f, i) => (
                  <tr key={`${f.path}-${f.location}-${i}`}>
                    <td className="mono">
                      {f.path}
                      {f.required ? <span className="chip acc ev-req">required</span> : null}
                    </td>
                    <td className="mono">{f.type ?? '–'}</td>
                    <td className="muted">{f.description ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * What Plume gives Claude for a session: a compact index (documents with field counts), and the fields of an API's
 * documents on demand, one page at a time (the server caps a page at about 20k characters).
 */
export function EvidencePack({ sessionId, apis }: { sessionId: string; apis: ApiRef[] }) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getModelContext(sessionId, signal),
    [client, sessionId],
  );
  const { state, retry } = useAsync(load);
  const [byApi, setByApi] = useState<Record<string, ApiState>>({});

  async function fetchPage(api: string, cursor?: number) {
    const prev = byApi[api];
    const loaded = prev && prev.status !== 'idle' ? prev.loaded : undefined;
    setByApi((s) => ({ ...s, [api]: { status: 'loading', loaded } }));
    try {
      const page = await client.getModelEvidence(sessionId, { api, cursor });
      setByApi((s) => ({ ...s, [api]: { status: 'ready', loaded: mergePage(loaded, page) } }));
    } catch (e) {
      setByApi((s) => ({
        ...s,
        [api]: {
          status: 'error',
          message: e instanceof Error ? e.message : 'Could not load the fields.',
          loaded,
        },
      }));
    }
  }

  if (state.status === 'loading') return <p className="muted small">Loading the evidence pack…</p>;
  if (state.status === 'error')
    return (
      <p role="alert" className="form-error">
        Could not load the evidence pack: {state.error.message}{' '}
        <button type="button" className="linkbtn small" onClick={retry}>
          Try again
        </button>
      </p>
    );

  const ctx = state.data;
  return (
    <div role="region" aria-label="Evidence pack" className="evidence-pack">
      {ctx.apis.map((a) => {
        const ref = apis.find((x) => x.id === a.api);
        const st: ApiState = byApi[a.api] ?? { status: 'idle' };
        const loaded = st.status === 'idle' ? undefined : st.loaded;
        const totalFields = a.documents.reduce((n, d) => n + d.fields, 0);
        return (
          <section
            key={a.api}
            className="ev-api"
            aria-label={`Evidence for ${ref?.shortName ?? a.api}`}
          >
            <h4>
              {ref?.shortName ?? a.api}{' '}
              <span className="mono faint small" title={a.build}>
                build {shortBuild(a.build)}
              </span>
            </h4>
            <ul className="ev-list">
              {a.documents.map((d) => (
                <li key={d.doc_id}>
                  <Chip>{d.kind}</Chip> <b>{d.title}</b>{' '}
                  {d.endpoint ? <span className="mono small">{d.endpoint}</span> : null}{' '}
                  <span className="faint small">{d.fields} fields</span>
                  {!d.complete ? <Chip tone="warn">partial schema</Chip> : null}
                </li>
              ))}
              {a.documents.length === 0 ? (
                <li className="muted small">No documents for this concept in this API.</li>
              ) : null}
            </ul>
            {a.documents.length > 0 && !loaded ? (
              <Button disabled={st.status === 'loading'} onClick={() => void fetchPage(a.api)}>
                {st.status === 'loading'
                  ? `Loading ${ref?.shortName ?? a.api} fields…`
                  : `Show ${ref?.shortName ?? a.api} fields (${totalFields})`}
              </Button>
            ) : null}
            {st.status === 'error' ? (
              <p role="alert" className="form-error">
                {st.message}{' '}
                <button
                  type="button"
                  className="linkbtn small"
                  onClick={() => void fetchPage(a.api, loaded?.next ?? undefined)}
                >
                  Try again
                </button>
              </p>
            ) : null}
            {loaded ? (
              <>
                <Fields docs={loaded.docs} />
                {loaded.missing.length ? (
                  <p className="muted small">
                    Not found in this build: {loaded.missing.join(', ')}
                  </p>
                ) : null}
                <p className="faint small" aria-live="polite">
                  {loaded.returned} of {loaded.total} fields shown
                </p>
                {loaded.next !== null ? (
                  <Button
                    disabled={st.status === 'loading'}
                    onClick={() => void fetchPage(a.api, loaded.next ?? undefined)}
                  >
                    {st.status === 'loading' ? 'Loading…' : 'Load more fields'}
                  </Button>
                ) : null}
              </>
            ) : null}
          </section>
        );
      })}
      {ctx.draft_format !== undefined ? (
        <details className="ev-format">
          <summary>Draft format</summary>
          {/* a scrollable region must be reachable with the keyboard */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <pre className="code payload" tabIndex={0} aria-label="Draft format">
            {JSON.stringify(ctx.draft_format, null, 2)}
          </pre>
        </details>
      ) : null}
      {ctx.next ? <p className="muted small">{ctx.next}</p> : null}
    </div>
  );
}
