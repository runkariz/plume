import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useIsMaintainer } from '@/app/authStore';
import { GenerateSession } from './GenerateSession';
import { ModelJobProgress } from './ModelJobProgress';
import { useAsync } from '@/api/useAsync';
import {
  ApiError,
  type ApiRef,
  type Concept,
  type GenerateResponse,
  isGenerateJob,
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
  Segmented,
} from '@/components';

type Filter = 'all' | 'every' | 'write';

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
  return (
    <article className="card concept">
      <div className="concept-name">
        <h3>{concept.name}</h3>
        <span className="faint small">~{concept.likelyFields} likely fields</span>
      </div>
      <p className="muted concept-desc">{concept.description}</p>
      <span className="concept-cov">
        {apis.map((a) => (
          <ApiAvatar
            key={a.id}
            text={a.logo.text}
            color={a.logo.color}
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
            aria-label={`Generate ${concept.name} with Claude instead`}
          >
            Use Claude instead
          </button>
        ) : null}
      </span>
    </article>
  );
}

function useSuggestions(key: string) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal): Promise<SuggestResponse> =>
      key === ''
        ? Promise.resolve({ apis: [], concepts: [], notModeled: { count: 0, summary: '' } })
        : client.suggestModels(key.split(','), signal),
    [client, key],
  );
  return useAsync(load);
}

export function Suggestions() {
  const client = useApiClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const key = (params.get('apis') ?? '').split(',').filter(Boolean).join(',');
  const apiIds = key === '' ? [] : key.split(',');
  const enough = apiIds.length >= 2;

  const { state, retry } = useSuggestions(key);
  const [filter, setFilter] = useState<Filter>('all');
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
  const suggestions = state.status === 'ready' ? state.data : null;
  const regenerateConcept = useMemo(() => {
    const want = regenerateWanted?.toLowerCase();
    return want
      ? suggestions?.concepts.find(
          (c) => c.id.toLowerCase() === want || c.name.toLowerCase() === want,
        )
      : undefined;
  }, [suggestions, regenerateWanted]);
  useEffect(() => {
    if (!regenerateConcept || autoStarted.current) return;
    autoStarted.current = true;
    void generate(regenerateConcept);
    // runs once per page load, when the concept to regenerate is known
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regenerateConcept]);
  const regenerateMissing = Boolean(regenerateWanted && suggestions && !regenerateConcept);
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

  const data = state.status === 'ready' ? state.data : null;
  const visible = (data?.concepts ?? []).filter((c) =>
    filter === 'every'
      ? Object.values(c.coverage).every((v) => v !== 'absent')
      : filter === 'write'
        ? c.operations.includes('write')
        : true,
  );

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
                  <ApiAvatar text={a.logo.text} color={a.logo.color} size={26} />
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
      {state.status === 'loading' ? <LoadingState label="Looking across the APIs" /> : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not suggest models"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {data && data.concepts.length === 0 ? (
        <EmptyState title="No shared concepts found">
          These APIs have no resources in common. Try a different selection.
        </EmptyState>
      ) : null}
      {data && data.concepts.length > 0 ? (
        <>
          <div className="opts">
            <Segmented
              variant="pills"
              label="Show concepts"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: 'All concepts' },
                { value: 'every', label: `In all ${data.apis.length} APIs` },
                { value: 'write', label: 'Can write' },
              ]}
            />
            <span className="legend" aria-label="Coverage legend">
              Coverage
              <span>
                <ApiAvatar text="W" color="#7f54b3" size={22} /> direct
              </span>
              <span>
                <ApiAvatar text="W" color="#7f54b3" kind="derived" size={22} /> derived
              </span>
              <span>
                <ApiAvatar text="W" color="#7f54b3" kind="absent" size={22} /> absent
              </span>
            </span>
          </div>
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
          <div className="concepts">
            {visible.length === 0 ? (
              <EmptyState title="No concepts match this filter">Try “All concepts”.</EmptyState>
            ) : (
              visible.map((c) => (
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
                {data.notModeled.count === 0
                  ? 'Every resource found in these APIs is part of a suggested concept.'
                  : `${data.notModeled.count} ${data.notModeled.summary}`}
              </p>
            </Card>
          </div>
        </>
      ) : null}
    </>
  );
}
