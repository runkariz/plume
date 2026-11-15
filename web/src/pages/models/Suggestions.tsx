import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useIsMaintainer } from '@/app/authStore';
import { GenerateSession } from './GenerateSession';
import { ModelJobProgress } from './ModelJobProgress';
import { Pager, SuggestControls } from './SuggestControls';
import {
  changed,
  isFiltered as isFilteredView,
  parseView,
  toQuery,
  withView,
  type SuggestView,
} from './suggestQuery';
import { useAsync } from '@/api/useAsync';
import {
  ApiError,
  type ApiCounts,
  type ApiRef,
  type Concept,
  type GenerateResponse,
  isGenerateJob,
  type SuggestQuery,
  type SuggestResponse,
} from '@/api/types';
import {
  ApiAvatar,
  Banner,
  Button,
  Card,
  Chip,
  Crumbs,
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components';

/** "Shopify · 2 models · 5 endpoints · 41 fields": only what the server counted, nothing for the API that lacks it. */
function countsLine(c: ApiCounts) {
  const parts = [
    c.models ? `${c.models} ${c.models === 1 ? 'model' : 'models'}` : null,
    c.endpoints ? `${c.endpoints} ${c.endpoints === 1 ? 'endpoint' : 'endpoints'}` : null,
    c.fields ? `${c.fields} fields` : null,
    c.operations.length ? c.operations.join(', ') : null,
  ].filter(Boolean);
  return parts.join(' · ');
}

function ConceptRow({
  concept,
  apis,
  busy,
  disabled,
  onGenerate,
  onGenerateWithClaude,
}: {
  concept: Concept;
  apis: ApiRef[];
  busy: boolean;
  disabled: boolean;
  onGenerate: () => void;
  /** Signed in only: the same model through your own Claude instead of the server. */
  onGenerateWithClaude?: () => void;
}) {
  const counts = apis.flatMap((a) => {
    const c = concept.apiCounts?.[a.id];
    const line = c ? countsLine(c) : '';
    return line ? [{ api: a, line }] : [];
  });
  return (
    <article className="card concept" aria-label={concept.name}>
      <div className="concept-main">
        <div className="concept-name">
          <h3>{concept.name}</h3>
          <span className="faint small">~{concept.likelyFields} likely fields</span>
        </div>
        <span className="concept-cov">
          {apis.map((a) => (
            <ApiAvatar
              key={a.id}
              text={a.logo.text}
              color={a.logo.color}
              url={a.logo.url}
              name={a.shortName}
              kind={concept.coverage[a.id] ?? 'absent'}
            />
          ))}
        </span>
        <span>
          <Chip>{concept.operations.join(', ')}</Chip>
        </span>
        <span>
          <Chip tone={concept.difficulty.tone}>{concept.difficulty.label}</Chip>
        </span>
        <span className="concept-actions">
          <Button
            variant="primary"
            size="lg"
            onClick={onGenerate}
            disabled={disabled}
            aria-busy={busy}
            aria-label={busy ? `Generating ${concept.name}` : `Generate ${concept.name}`}
          >
            {busy ? 'Generating…' : 'Generate'}
          </Button>
          {onGenerateWithClaude ? (
            <button
              type="button"
              className="linkbtn small"
              disabled={disabled}
              onClick={onGenerateWithClaude}
              aria-label={`Use Claude instead to generate ${concept.name}`}
            >
              Use Claude instead
            </button>
          ) : null}
        </span>
      </div>
      {concept.reason ? <p className="concept-reason muted">{concept.reason}</p> : null}
      {counts.length ? (
        <ul className="concept-counts" aria-label={`${concept.name} in each API`}>
          {counts.map(({ api, line }) => (
            <li key={api.id}>
              <ApiAvatar text={api.logo.text} color={api.logo.color} url={api.logo.url} size={18} />
              <b>{api.shortName}</b> <span className="faint">{line}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

/**
 * The suggestions of one query (the filters are in the URL). The previous answer stays on screen, dimmed, while the
 * next one loads, so searching and paging do not flash an empty page.
 */
function useSuggestions(apis: string[], query: SuggestQuery) {
  const client = useApiClient();
  const key = JSON.stringify([apis, query]);
  const [state, setState] = useState<{
    data: SuggestResponse | null;
    loading: boolean;
    error: Error | null;
  }>({ data: null, loading: true, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const [a, q] = JSON.parse(key) as [string[], SuggestQuery];
    if (a.length < 2) return;
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- a new query starts loading, the old answer stays
    setState((s) => ({ ...s, loading: true, error: null }));
    client.suggestModels(a, q, ctrl.signal).then(
      (data) => {
        if (!ctrl.signal.aborted) setState({ data, loading: false, error: null });
      },
      (error: unknown) => {
        if (!ctrl.signal.aborted)
          setState((s) => ({
            ...s,
            loading: false,
            error: error instanceof Error ? error : new Error(String(error)),
          }));
      },
    );
    return () => ctrl.abort();
  }, [client, key, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}

export function Suggestions() {
  const client = useApiClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const key = (params.get('apis') ?? '').split(',').filter(Boolean).join(',');
  const apiIds = useMemo(() => (key === '' ? [] : key.split(',')), [key]);
  const enough = apiIds.length >= 2;

  // the filters, the scope and the page are in the URL: a link keeps them
  const view = useMemo(() => parseView(params, apiIds), [params, apiIds]);
  const query = useMemo(() => toQuery(view), [view]);
  const { data, loading, error: loadError, retry } = useSuggestions(apiIds, query);
  // Every change starts from the latest URL, not the one of the last render: the router applies a navigation a
  // moment later, and two quick clicks (two checkboxes) must both count.
  const latest = useRef(params);
  useEffect(() => {
    latest.current = params;
  }, [params]);
  const update = useCallback(
    (f: (v: SuggestView) => SuggestView) => {
      const next = withView(latest.current, f(parseView(latest.current, apiIds)));
      latest.current = next;
      setParams(next, { replace: true });
    },
    [setParams, apiIds],
  );
  const setView = useCallback((v: SuggestView) => update(() => v), [update]);
  const [resetKey, setResetKey] = useState(0);
  const [generating, setGenerating] = useState<string | null>(null);
  const [session, setSession] = useState<{ concept: Concept; response: GenerateResponse } | null>(
    null,
  );
  const [job, setJob] = useState<{ concept: Concept; jobId: string } | null>(null);
  // server generation is not configured (503): offer the Claude flow for this concept
  const [fallback, setFallback] = useState<Concept | null>(null);
  const maintainer = useIsMaintainer();
  const [error, setError] = useState<string | null>(null);
  const ctrl = useRef<AbortController | null>(null);
  const openModel = useCallback(
    (id: string, extra?: { ownerKey?: string }) =>
      navigate(
        `/models/${id}`,
        extra?.ownerKey ? { state: { ownerKey: extra.ownerKey } } : undefined,
      ),
    [navigate],
  );
  // "Regenerate" on a stale model lands here with ?regenerate=<concept>: open that concept's session once
  const regenerateWanted = params.get('regenerate');
  const autoStarted = useRef(false);
  // the concept to regenerate may not be on the current page (paging, filters): look it up on its own
  const lookup = useCallback(
    async (signal: AbortSignal) =>
      regenerateWanted && apiIds.length >= 2
        ? client.suggestModels(apiIds, { q: regenerateWanted, only: 'all', limit: 100 }, signal)
        : null,
    [client, apiIds, regenerateWanted],
  );
  const { state: lookupState } = useAsync(lookup);
  const lookedUp = lookupState.status === 'ready' ? lookupState.data : null;
  const regenerateConcept = useMemo(() => {
    const want = regenerateWanted?.toLowerCase();
    return want
      ? lookedUp?.concepts.find((c) => c.id.toLowerCase() === want || c.name.toLowerCase() === want)
      : undefined;
  }, [lookedUp, regenerateWanted]);
  useEffect(() => {
    if (!regenerateConcept || autoStarted.current) return;
    autoStarted.current = true;
    void generate(regenerateConcept);
    // runs once per page load, when the concept to regenerate is known
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regenerateConcept]);
  const regenerateMissing = Boolean(regenerateWanted && lookedUp && !regenerateConcept);
  useEffect(() => () => ctrl.current?.abort(), []);

  const crumbs = [
    { label: 'APIs', to: '/' },
    { label: 'Create a model', to: `/models?apis=${key}` },
    { label: 'Suggestions' },
  ];

  if (!enough)
    return (
      <>
        <Crumbs items={crumbs} />
        <EmptyState title="Pick at least two APIs">
          <Link to="/models">Choose the APIs to unify</Link>
        </EmptyState>
      </>
    );

  async function generate(concept: Concept, engine?: 'claude' | 'server') {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setGenerating(concept.id);
    setError(null);
    setFallback(null);
    try {
      const res = await client.generateModel(
        { apis: apiIds, concept: concept.id, ...(engine ? { engine } : {}) },
        c.signal,
      );
      if (isGenerateJob(res)) {
        // signed in: the model is written on the server, the page follows the job
        setJob({ concept, jobId: res.jobId });
        setGenerating(null);
        return;
      }
      if (res.status === 'ready' && res.snapshotId) {
        // a snapshot already exists for these builds: open it
        navigate(`/models/${res.snapshotId}`);
        return;
      }
      setSession({ concept, response: res });
      setGenerating(null);
    } catch (e) {
      if (c.signal.aborted) return;
      if (e instanceof ApiError && e.code === 'llm_unavailable') setFallback(concept);
      setError(
        e instanceof ApiError && e.code === 'llm_unavailable'
          ? 'Server-side generation is not configured on this Plume. You can generate it with Claude instead.'
          : e instanceof ApiError && e.status === 401
            ? 'Your session is not valid any more. Sign in again, or generate it with Claude.'
            : e instanceof ApiError && e.status === 429
              ? 'Too many generations right now. Try again in a minute.'
              : e instanceof Error
                ? e.message
                : 'Generation failed.',
      );
      setGenerating(null);
    }
  }

  const filtered = isFilteredView(view);

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">Suggested models</h1>
          {data ? (
            <ul className="selbar-chips plain" aria-label="Selected APIs">
              {data.apis.map((a) => (
                <li key={a.id} className="selbar-chip light">
                  <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={26} />
                  {a.shortName}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <Link className="btn" to={`/models?apis=${key}`}>
          Change APIs
        </Link>
      </div>
      {!data && loading ? <LoadingState label="Looking across the APIs" /> : null}
      {loadError && !data ? (
        <ErrorState title="Could not suggest models" message={loadError.message} onRetry={retry} />
      ) : null}
      {data ? (
        <>
          <SuggestControls
            clearSignal={resetKey}
            apis={data.apis}
            view={view}
            counts={data.counts}
            onChange={update}
            onClear={() => {
              setResetKey((n) => n + 1);
              setView({ q: '', only: 'multi', require: [], chip: 'all', page: 1 });
            }}
          />
          {loadError ? (
            <ErrorState
              title="Could not update the suggestions"
              message={loadError.message}
              onRetry={retry}
            />
          ) : null}
          {regenerateMissing ? (
            <p role="alert" className="form-error">
              “{regenerateWanted}” is not suggested for these APIs any more. Pick a concept below.
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="form-error">
              {error}
              {fallback ? (
                <>
                  {' '}
                  <button
                    type="button"
                    className="linkbtn"
                    onClick={() => void generate(fallback, 'claude')}
                  >
                    Use Claude instead
                  </button>
                </>
              ) : null}
            </p>
          ) : null}
          {job ? (
            <ModelJobProgress
              key={job.jobId}
              concept={job.concept}
              jobId={job.jobId}
              onOpen={openModel}
              onCancel={() => setJob(null)}
              onUseClaude={() => {
                const c = job.concept;
                setJob(null);
                void generate(c, 'claude');
              }}
            />
          ) : null}
          {session ? (
            <GenerateSession
              concept={session.concept}
              apis={data.apis}
              session={session.response}
              onOpen={openModel}
              onCancel={() => setSession(null)}
            />
          ) : null}
          <div
            id="concept-list"
            className={`concepts${loading ? ' loading' : ''}`}
            aria-busy={loading}
          >
            {data.concepts.length === 0 ? (
              data.total > 0 ? (
                <EmptyState title="That page is empty">
                  <button
                    type="button"
                    className="linkbtn"
                    onClick={() => setView({ ...view, page: 1 })}
                  >
                    Back to the first page
                  </button>
                </EmptyState>
              ) : filtered ? (
                <EmptyState title="No concepts match these filters">
                  <button
                    type="button"
                    className="linkbtn"
                    onClick={() => {
                      setResetKey((n) => n + 1);
                      setView({ q: '', only: 'multi', require: [], chip: 'all', page: 1 });
                    }}
                  >
                    Clear the filters
                  </button>
                </EmptyState>
              ) : (
                <EmptyState title="No shared concepts found">
                  These APIs have no resources in common. Try a different selection.
                </EmptyState>
              )
            ) : (
              data.concepts.map((c) => (
                <ConceptRow
                  key={c.id}
                  concept={c}
                  apis={data.apis}
                  busy={generating === c.id}
                  disabled={generating !== null || session !== null || job !== null}
                  onGenerate={() => void generate(c)}
                  onGenerateWithClaude={maintainer ? () => void generate(c, 'claude') : undefined}
                />
              ))
            )}
          </div>
          <Pager
            data={data}
            page={view.page}
            onPage={(page) => {
              setView({ ...view, page });
              document.getElementById('concept-list')?.scrollIntoView?.({ block: 'start' });
            }}
          />
          <div className="two even">
            <Banner
              tone="accent"
              title={maintainer ? 'Generate runs on the server' : 'Using Claude instead?'}
            >
              {maintainer ? (
                <>
                  You are signed in: Generate writes the model on the server and the result stays{' '}
                  <b>unreleased</b> until you release it. Prefer your own Claude? Ask “which models
                  can I create from {data.apis.map((a) => a.shortName).join(', ')}?” through the
                  connector.
                </>
              ) : (
                <>
                  Ask “which models can I create from {data.apis.map((a) => a.shortName).join(', ')}
                  ?” The same suggestions come back through the Plume connector, and Claude can
                  generate the model for you. Models made this way are <b>unlisted</b>: only people
                  with the link can open them.
                </>
              )}
            </Banner>
            <Card className="pad">
              <h2 className="h2-sm">Not modeled</h2>
              <p className="muted">
                {view.q || view.require.length
                  ? // the server's summary is for the whole selection: with filters, say what the filters leave
                    data.counts.single === 0
                    ? 'No concept that exists in only one API matches these filters.'
                    : `${data.counts.single} ${data.counts.single === 1 ? 'concept' : 'concepts'} that exist in only one of these APIs match these filters.`
                  : data.notModeled.count === 0
                    ? 'Every resource found in these APIs is part of a suggested concept.'
                    : `${data.notModeled.count} ${data.notModeled.summary}`}
              </p>
              {data.counts.single > 0 || data.notModeled.count > 0 ? (
                view.only === 'single' ? (
                  <Button onClick={() => update((v) => changed(v, { only: 'multi' }))}>
                    Back to concepts shared by several APIs
                  </Button>
                ) : data.counts.single > 0 ? (
                  <Button
                    onClick={() => update((v) => changed(v, { only: 'single', chip: 'all' }))}
                  >
                    Browse the concepts that exist in only one API
                  </Button>
                ) : null
              ) : null}
            </Card>
          </div>
        </>
      ) : null}
    </>
  );
}
