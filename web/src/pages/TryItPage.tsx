import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { picksFromNote, withPick, type CheckPick } from '@/lib/checkPicks';
import { docHref, endpointOfId, operationOf, shownPath } from '@/lib/docHref';
import { formatMs } from '@/lib/format';
import {
  ApiError,
  type AskResponse,
  type CheckCallResponse,
  type HttpMethod,
  type KindFilter,
  type SearchMode,
  type SearchResponse,
  type TraceStep,
} from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import {
  Button,
  Card,
  Chip,
  Crumbs,
  EmptyState,
  ErrorState,
  LoadingState,
  MethodBadge,
  ScoreBar,
  Segmented,
  type Crumb,
} from '@/components';

type Tool = 'search' | 'ask' | 'check';

const TOOLS = [
  { value: 'search', label: 'Search' },
  { value: 'ask', label: 'Ask' },
  { value: 'check', label: 'Check call' },
] as const;
const MODES: { value: SearchMode; label: string }[] = [
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'dense', label: 'Dense only' },
  { value: 'text', label: 'Text only' },
];
const KINDS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: 'All kinds' },
  { value: 'endpoint', label: 'Endpoints' },
  { value: 'model', label: 'Models' },
  { value: 'guide', label: 'Guides' },
];
const METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const TOP_K = 5;

const SOURCE_LABEL: Record<TraceStep['source'], string> = {
  gemini: 'Gemini',
  embedder: 'Embedder',
  postgres: 'Postgres',
  plume: 'Plume',
};

export function QueryTrace({ trace, totalMs }: { trace: TraceStep[]; totalMs: number }) {
  return (
    <Card className="pad">
      <h2 className="h2-sm">Query trace</h2>
      <ul className="trace">
        {trace.map((t, i) => (
          <li key={i} className="trace-row">
            <span className={`log-src ${t.source}`}>{SOURCE_LABEL[t.source]}</span>
            <span>{t.label}</span>
            <span className="ms mono">{formatMs(t.ms)}</span>
          </li>
        ))}
        <li className="trace-row total">
          <b>Total</b>
          <span className="ms mono">{formatMs(totalMs)}</span>
        </li>
      </ul>
    </Card>
  );
}

type Run<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T };

/** Runs one call at a time; a newer run aborts the older one. */
function useRun<T>() {
  const [run, setRun] = useState<Run<T>>({ status: 'idle' });
  const ctrl = useRef<AbortController | null>(null);
  useEffect(() => () => ctrl.current?.abort(), []);
  const start = useCallback((fn: (signal: AbortSignal) => Promise<T>) => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setRun({ status: 'loading' });
    fn(c.signal).then(
      (data) => {
        if (!c.signal.aborted) setRun({ status: 'ready', data });
      },
      (e: unknown) => {
        if (!c.signal.aborted)
          setRun({ status: 'error', message: e instanceof Error ? e.message : String(e) });
      },
    );
  }, []);
  const reset = useCallback(() => {
    ctrl.current?.abort();
    setRun({ status: 'idle' });
  }, []);
  return { run, start, reset };
}

function RunState<T>({
  run,
  idle,
  children,
}: {
  run: Run<T>;
  idle: string;
  children: (data: T) => React.ReactNode;
}) {
  if (run.status === 'idle') return <EmptyState title="Nothing run yet">{idle}</EmptyState>;
  if (run.status === 'loading') return <LoadingState label="Running" />;
  if (run.status === 'error') return <ErrorState title="The call failed" message={run.message} />;
  return <>{children(run.data)}</>;
}

function SearchTool({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const [query, setQuery] = useState('How do I paginate through orders?');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [kind, setKind] = useState<KindFilter>('all');
  const { run, start } = useRun<SearchResponse>();

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    start((signal) =>
      client.search(apiId, { query: query.trim(), mode, kind, topK: TOP_K }, signal),
    );
  }

  return (
    <>
      <form className="card qbox" onSubmit={submit} role="search">
        <label htmlFor="try-query" className="sr-only">
          Question or search text
        </label>
        <input
          id="try-query"
          className="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask about this API"
        />
        <Button variant="primary" type="submit" size="lg">
          Run
        </Button>
      </form>
      <div className="opts">
        <Segmented
          variant="pills"
          label="Search mode"
          options={MODES}
          value={mode}
          onChange={setMode}
        />
        <Segmented variant="pills" label="Kind" options={KINDS} value={kind} onChange={setKind} />
        <span className="faint" style={{ marginLeft: 'auto' }}>
          Top {TOP_K}
        </span>
      </div>
      <div className="try-cols">
        <div className="stack" aria-live="polite">
          <RunState run={run} idle="Run a search to see ranked results and the query trace.">
            {(d) =>
              d.results.length === 0 ? (
                <EmptyState title="No results">Try other words or a different kind.</EmptyState>
              ) : (
                <ol className="results">
                  {d.results.map((h, i) => (
                    <li key={h.id}>
                      <Card className={`res${i === 0 ? ' first' : ''}`}>
                        <span className="rank" aria-label={`Rank ${i + 1}`}>
                          {i + 1}
                        </span>
                        <div className="res-body">
                          <div className="res-title">
                            <h3>{h.title}</h3>
                            <Chip>{h.kind}</Chip>
                          </div>
                          <div className="mono muted">{h.subtitle}</div>
                          <p className="muted">{h.snippet}</p>
                          <div className="sc">
                            <span>dense {h.denseRank ? `#${h.denseRank}` : '–'}</span>
                            <ScoreBar value={h.denseScore} label="dense" />
                            <span>text {h.textRank ? `#${h.textRank}` : '–'}</span>
                            <ScoreBar value={h.textScore} label="text" />
                            <span>
                              fused <b>{h.fused.toFixed(4)}</b>
                            </span>
                          </div>
                        </div>
                      </Card>
                    </li>
                  ))}
                </ol>
              )
            }
          </RunState>
        </div>
        <div className="stack">
          {run.status === 'ready' ? (
            <>
              <QueryTrace trace={run.data.trace} totalMs={run.data.totalMs} />
              <Card className="pad">
                <h2 className="h2-sm">What Claude receives</h2>
                {/* a scrollable region must be reachable with the keyboard */}
                {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
                <pre className="code payload" tabIndex={0} aria-label="Reader tool response">
                  {run.data.claudePayload}
                </pre>
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}

function AskTool({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const [question, setQuestion] = useState('Can I cancel a fulfilled order?');
  const { run, start } = useRun<AskResponse>();

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    start((signal) => client.ask(apiId, question.trim(), signal));
  }

  return (
    <>
      <form className="card qbox" onSubmit={submit} role="search">
        <label htmlFor="ask-q" className="sr-only">
          Your question
        </label>
        <input
          id="ask-q"
          className="q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button variant="primary" type="submit" size="lg">
          Ask
        </Button>
      </form>
      <p className="faint small" style={{ margin: '12px 0 18px' }}>
        Plume retrieves; Claude writes the answer. These are the passages it would receive.
      </p>
      <div className="try-cols">
        <div className="stack" aria-live="polite">
          <RunState run={run} idle="Ask a question to see the passages Claude would answer from.">
            {(d) =>
              d.passages.length === 0 ? (
                <EmptyState title="Not documented in this build">
                  No passage matched. Plume never answers from a guess.
                </EmptyState>
              ) : (
                <ol className="results">
                  {d.passages.map((p, i) => (
                    <li key={p.id}>
                      <Card className={`res${i === 0 ? ' first' : ''}`}>
                        <span className="rank">{i + 1}</span>
                        <div className="res-body">
                          <h3>{p.title}</h3>
                          <blockquote className="quote">{p.quote}</blockquote>
                          {p.sourceUrl ? (
                            <a
                              className="small"
                              href={p.sourceUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              Source
                            </a>
                          ) : null}
                        </div>
                      </Card>
                    </li>
                  ))}
                </ol>
              )
            }
          </RunState>
        </div>
        <div className="stack">
          {run.status === 'ready' ? (
            <QueryTrace trace={run.data.trace} totalMs={run.data.totalMs} />
          ) : null}
        </div>
      </div>
    </>
  );
}

/**
 * What to do with an "ambiguous" answer: the examples the server named as buttons that fill the parameter and check
 * again, and some of the operations at that path as links to their pages.
 */
function AmbiguousPicks({
  apiId,
  picks,
  alternatives,
  onPick,
}: {
  apiId: string;
  picks: CheckPick[];
  alternatives: string[];
  onPick: (p: CheckPick) => void;
}) {
  if (picks.length === 0 && alternatives.length === 0) return null;
  return (
    <div className="check-picks" style={{ marginBottom: 10 }}>
      {picks.length ? (
        <>
          <p className="small muted">Pick one to fill the parameter and check again:</p>
          <div className="row check-pick-row" role="group" aria-label="Examples to pick">
            {picks.map((p) => (
              <button
                key={`${p.key}=${p.value}`}
                type="button"
                className="btn sm mono check-pick"
                onClick={() => onPick(p)}
              >
                {p.key}={p.value}
              </button>
            ))}
          </div>
        </>
      ) : null}
      {alternatives.length ? (
        <details className="check-alternatives">
          <summary className="small">Some of the operations at this path</summary>
          <ul className="linked-list" aria-label="Operations at this path">
            {alternatives.map((id) => (
              <li key={id}>
                <Link to={docHref(apiId, id)} className="mono small" title={id}>
                  {endpointOfId(id)?.operation ?? id}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function CheckTool({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const [method, setMethod] = useState<HttpMethod>('GET');
  const [path, setPath] = useState('/admin/api/latest/orders.json');
  const [params, setParams] = useState('limit, page_info');
  const { run, start } = useRun<CheckCallResponse>();

  function check(paramsText: string) {
    if (!path.trim()) return;
    start((signal) =>
      client.checkCall(
        apiId,
        {
          method,
          path: path.trim(),
          params: paramsText
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
        },
        signal,
      ),
    );
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    check(params);
  }

  /** An example the server gave for an ambiguous call: it goes into the parameters and the check runs again. */
  function pick(p: CheckPick) {
    const next = withPick(params, p);
    setParams(next);
    check(next);
  }

  return (
    <>
      <form className="card qbox" onSubmit={submit}>
        <label htmlFor="chk-method" className="sr-only">
          HTTP method
        </label>
        <select
          id="chk-method"
          className="input method-select"
          value={method}
          onChange={(e) => setMethod(e.target.value as HttpMethod)}
        >
          {METHODS.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <label htmlFor="chk-path" className="sr-only">
          Path
        </label>
        <input
          id="chk-path"
          className="q mono"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <label htmlFor="chk-params" className="sr-only">
          Parameters, comma separated
        </label>
        <input
          id="chk-params"
          className="q mono params-input"
          value={params}
          onChange={(e) => setParams(e.target.value)}
          placeholder="params, comma separated"
        />
        <Button variant="primary" type="submit" size="lg">
          Check
        </Button>
      </form>
      <div className="try-cols" style={{ marginTop: 22 }}>
        <div className="stack" aria-live="polite">
          <RunState run={run} idle="Check whether a call (method, path, parameters) is documented.">
            {(d) => (
              <Card className="pad">
                <div className="row" style={{ marginBottom: 12 }}>
                  <Chip tone={d.verdict === 'documented' ? 'ok' : 'warn'} dot>
                    {d.verdict === 'documented'
                      ? 'Documented'
                      : d.verdict === 'ambiguous'
                        ? 'Several operations share this method and path'
                        : `Not documented in build ${d.build}`}
                  </Chip>
                  {!d.complete ? <Chip tone="warn">Schema partial: absence not proven</Chip> : null}
                </div>
                {d.matched ? (
                  <div className="row" style={{ marginBottom: 10 }}>
                    <MethodBadge method={d.matched.method} />
                    <span className="mono">{shownPath(d.matched)}</span>
                    {operationOf(d.matched.id, d.matched.method, d.matched.path) ? (
                      <span className="faint small mono">
                        · {operationOf(d.matched.id, d.matched.method, d.matched.path)}
                      </span>
                    ) : null}
                  </div>
                ) : null}
                {d.verdict !== 'ambiguous' && d.alternatives && d.alternatives.length > 0 ? (
                  <p className="small muted" style={{ marginBottom: 10 }}>
                    Other operations at the same method and path:{' '}
                    {d.alternatives.map((a, i) => (
                      <span key={a}>
                        {i > 0 ? ', ' : ''}
                        <span className="mono">{a}</span>
                      </span>
                    ))}
                    . The check matched the one shown above.
                  </p>
                ) : null}
                {d.note ? (
                  <p className="cite warn" role="note" style={{ marginBottom: 10 }}>
                    {d.note}
                  </p>
                ) : null}
                {d.verdict === 'ambiguous' ? (
                  <AmbiguousPicks
                    apiId={apiId}
                    picks={picksFromNote(d.note)}
                    alternatives={d.alternatives ?? []}
                    onPick={pick}
                  />
                ) : null}
                <ul className="checks">
                  {d.paramChecks.map((p) => (
                    <li key={p.name}>
                      <Chip tone={p.found ? 'ok' : 'bad'}>{p.found ? 'found' : 'missing'}</Chip>
                      <span className="mono">{p.name}</span>
                      {p.where ? <span className="faint small">in {p.where}</span> : null}
                    </li>
                  ))}
                </ul>
                <p className="faint small" style={{ marginTop: 12 }}>
                  Checked {d.checked.endpoints} endpoints and {d.checked.models} models.
                  {d.verdict === 'ambiguous'
                    ? ' Nothing was decided: say which operation, then check again.'
                    : ` Wording rule: "not documented in build ${d.build}", never "does not exist".`}
                </p>
              </Card>
            )}
          </RunState>
        </div>
      </div>
    </>
  );
}

export function TryItPage() {
  const { apiId = '' } = useParams();
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const [tool, setTool] = useState<Tool>('search');
  const load = useCallback((signal: AbortSignal) => client.getApi(apiId, signal), [client, apiId]);
  const { state, retry } = useAsync(load);

  const name = state.status === 'ready' ? state.data.name.replace(/ API$/, '') : 'API';
  const crumbs: Crumb[] = [
    maintainer ? { label: 'Maintainer', to: '/maintainer' } : { label: 'APIs', to: '/' },
    { label: name, to: `/apis/${apiId}` },
    { label: 'Try it' },
  ];

  if (state.status === 'error') {
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'API not found'
              : 'Could not load this API'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  }

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <h1 className="h1-sm">Try it</h1>
        <div className="row">
          {state.status === 'ready' ? (
            <span className="chip build-chip">
              Build {state.data.index.build ?? 'none'} ·{' '}
              {state.data.isLive
                ? 'live'
                : state.data.status.kind === 'unpublished'
                  ? 'not published'
                  : 'updating'}
            </span>
          ) : null}
          <Segmented label="Tool" options={[...TOOLS]} value={tool} onChange={setTool} />
        </div>
      </div>
      {tool === 'search' ? <SearchTool apiId={apiId} /> : null}
      {tool === 'ask' ? <AskTool apiId={apiId} /> : null}
      {tool === 'check' ? <CheckTool apiId={apiId} /> : null}
    </>
  );
}
