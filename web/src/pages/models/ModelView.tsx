import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useIsMaintainer } from '@/app/authStore';
import { useAsync } from '@/api/useAsync';
import { ApiError, type CollectionRef, type ModelSnapshot } from '@/api/types';
import {
  ApiAvatar,
  Banner,
  Button,
  Card,
  Chip,
  Crumbs,
  ErrorState,
  LoadingState,
  Segmented,
} from '@/components';
import { shortBuild } from '@/lib/format';
import { Operations } from './Operations';
import { VerifiedMappings } from './VerifiedMappings';
import { apiLabel } from '@/lib/names';
import { richText } from '@/lib/richText';
import { docHref } from '@/lib/docHref';
import { countLeaves } from './fields';
import { MappingTable } from './MappingTable';
import { ModelWorkbench } from './ModelWorkbench';
import {
  effectiveSelection,
  parseModelView,
  toggleApi,
  withModelView,
  type ModelViewState,
} from './modelView';
import {
  LineageHistory,
  RetirePanel,
  SameConceptLine,
  SupersededBanner,
  SupersedesLine,
  LineageLine,
  CollectionNotice,
  ReviewBanner,
  ReviseCard,
  ShareCard,
  VisibilityChip,
} from './ModelAccess';
import { ModelWarnings } from './ModelWarnings';
import { ImpactBanner } from './ImpactBanner';
import { StaleChip } from './StaleChip';
import { ImpactChip } from '@/components/ImpactChip';

export function claudePrompt(s: ModelSnapshot): string {
  const apis = s.inputs.map((a) => a.shortName).join(', ');
  return (
    `Use the Plume connector. Call get_snapshot with id "${s.id}": the canonical ${s.name} model for ${apis}. ` +
    `It was generated and is unverified, so check each mapping with search_docs, get_endpoint and find_field ` +
    `before you write any mapping code.`
  );
}

function staleSentence(s: ModelSnapshot): string {
  const names = (s.staleInputs ?? []).map((i) => apiLabel({ id: i.api }));
  return names.length
    ? `The docs of ${names.join(', ')} changed after it was built.`
    : 'The docs changed after it was built.';
}

/** Above this many fields a model opens as a table, and the graph focuses on one field. */
export const BIG_MODEL = 12;

export function ModelView() {
  const { snapshotId = '' } = useParams();
  const maintainer = useIsMaintainer();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getSnapshot(snapshotId, signal),
    [client, snapshotId],
  );
  const { state, retry } = useAsync(load);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');
  // right after someone without a token started their My models collection with this model: its link, shown once
  // (then dropped from the history)
  const location = useLocation();
  const navigate = useNavigate();
  const [arrival] = useState<CollectionRef | null>(
    () => (location.state as { collection?: CollectionRef } | null)?.collection ?? null,
  );
  const [noticeOpen, setNoticeOpen] = useState(arrival !== null);
  useEffect(() => {
    if (arrival) navigate(location.pathname + location.search, { replace: true, state: null });
    // once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const snap = state.status === 'ready' ? state.data : null;
  // the view, the filter, the checked APIs and the selected mapping are in the URL: a link keeps them
  const [params, setParams] = useSearchParams();
  const mv = useMemo(() => (snap ? parseModelView(params, snap) : null), [params, snap]);
  const latest = useRef(params);
  useEffect(() => {
    latest.current = params;
  }, [params]);
  // every change starts from the latest URL (two quick clicks must both count)
  const update = useCallback(
    (f: (v: ModelViewState) => ModelViewState) => {
      if (!snap) return;
      const next = withModelView(latest.current, f(parseModelView(latest.current, snap)));
      latest.current = next;
      setParams(next, { replace: true });
    },
    [snap, setParams],
  );
  const selection = snap && mv ? effectiveSelection(snap, mv) : null;

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
    setTimeout(() => setCopied('idle'), 2500);
  }

  const crumbs = [{ label: 'Models', to: '/models' }, { label: snap?.name ?? 'Model' }];

  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Model not found'
              : 'Could not load this model'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  if (!snap)
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the model" />
      </>
    );

  const prompt = claudePrompt(snap);
  const big = countLeaves(snap) > BIG_MODEL;
  // null in the URL = the default for the model size (a big model opens as a table, with the graph on one field)
  const view = mv?.view ?? (big ? 'table' : 'graph');
  const scope = mv?.scope ?? (big ? 'field' : 'all');

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{snap.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <VisibilityChip visibility={snap.visibility} />
            <Chip tone="warn">Generated, unverified</Chip>
            {snap.impact ? (
              <ImpactChip impact={snap.impact} />
            ) : snap.stale ? (
              <StaleChip inputs={snap.staleInputs} />
            ) : null}
            <Chip>{snap.inputs.length} APIs</Chip>
            <Chip>{countLeaves(snap)} fields</Chip>
            <Chip>snapshot {snap.id}</Chip>
          </div>
          <LineageLine snap={snap} />
        </div>
        <div className="row">
          {snap.inputs.length >= 2 ? (
            <Link
              className="btn"
              to={`/models/related?apis=${snap.inputs.map((i) => i.id).join(',')}&concept=${encodeURIComponent(snap.concept ?? snap.name)}`}
            >
              Related concepts
            </Link>
          ) : null}
          <Button onClick={() => void copy(prompt)}>Copy for Claude</Button>
          {/* claude.ai/new?q= pre-filling could not be verified, so: copy the prompt, then open a new chat to paste it. */}
          <a
            className="btn primary"
            href="https://claude.ai/new"
            target="_blank"
            rel="noreferrer"
            onClick={() => void copy(prompt)}
          >
            Open in Claude
          </a>
          <span role="status" className="faint small">
            {copied === 'ok'
              ? 'Prompt copied: paste it into Claude'
              : copied === 'fail'
                ? 'Copy failed: select the text instead'
                : ''}
          </span>
        </div>
      </div>
      {arrival && noticeOpen ? (
        <div className="access-banner">
          <CollectionNotice collection={arrival} onClose={() => setNoticeOpen(false)} />
        </div>
      ) : null}
      <div className="access-banner">
        <ReviewBanner snap={snap} onChanged={() => retry()} />
        <LineageHistory snap={snap} />
        <SupersededBanner snap={snap} />
        <RetirePanel snap={snap} onChanged={() => retry()} />
        <SupersedesLine snap={snap} />
        <SameConceptLine snap={snap} />
        <ModelWarnings snap={snap} />
      </div>
      {snap.impact ? <ImpactBanner snap={snap} /> : null}
      {!snap.impact && snap.stale ? (
        <div className="stale-banner">
          <Banner tone="warn" title="This model is built on older docs">
            {staleSentence(snap)} The mappings and citations below are still checked against the
            builds this model was made from, but they may not match the docs as they are now.
            Regenerate to rebuild the model from the current docs.
            <ul className="stale-builds">
              {(snap.staleInputs ?? []).map((i) => (
                <li key={i.api}>
                  <span className="mono">{apiLabel({ id: i.api })}</span>: built on{' '}
                  <span className="mono" title={i.pinned}>
                    {shortBuild(i.pinned)}
                  </span>
                  , now{' '}
                  <span className="mono" title={i.current}>
                    {shortBuild(i.current)}
                  </span>
                </li>
              ))}
            </ul>
            <div className="row">
              <Link
                className="btn primary"
                to={`/models/suggest?apis=${snap.inputs.map((a) => a.id).join(',')}&regenerate=${encodeURIComponent(snap.concept ?? snap.name)}`}
              >
                Regenerate
              </Link>
              <span className="faint small">Opens a new generation session for {snap.name}.</span>
            </div>
          </Banner>
        </div>
      ) : null}
      <div className="legend-line muted small">
        <span>
          <svg width="28" height="6" aria-hidden>
            <line x1="0" y1="3" x2="28" y2="3" stroke="currentColor" strokeWidth="2" />
          </svg>{' '}
          direct
        </span>
        <span>
          <svg width="28" height="6" aria-hidden>
            <line
              x1="0"
              y1="3"
              x2="28"
              y2="3"
              stroke="currentColor"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
          </svg>{' '}
          derived or transformed
        </span>
        <span>no edge = not supported</span>
      </div>
      <div className="view-switch">
        <Segmented
          label="View"
          value={view}
          onChange={(v) => update((s0) => ({ ...s0, view: v }))}
          options={[
            { value: 'table', label: 'Table' },
            { value: 'graph', label: 'Graph' },
          ]}
        />
        {view === 'graph' && big ? (
          <Segmented
            label="Graph shows"
            variant="pills"
            value={scope}
            onChange={(v) => update((s0) => ({ ...s0, scope: v }))}
            options={[
              { value: 'field', label: 'Selected field' },
              { value: 'all', label: 'Whole model' },
            ]}
          />
        ) : null}
        <span className="faint small">
          {view === 'table'
            ? 'Every field and how each API fills it, with its citations.'
            : scope === 'field'
              ? 'Pick a mapping in the list on the left to see it here.'
              : 'Scroll to pan, Ctrl or ⌘ + scroll to zoom. Pick a mapping in the list on the left to zoom to it.'}
        </span>
      </div>
      {view === 'table' ? (
        <MappingTable snapshot={snap} />
      ) : (
        <ModelWorkbench
          snap={snap}
          scope={scope}
          readable={big}
          text={mv?.f ?? ''}
          show={mv?.show ?? null}
          selection={selection}
          onText={(f) => update((s0) => ({ ...s0, f }))}
          onToggleApi={(id, on) =>
            update((s0) => ({ ...s0, show: toggleApi(snap, s0.show, id, on) }))
          }
          onSelect={(sel) => update((s0) => ({ ...s0, selection: sel }))}
          renderDocLink={(apiId, docId) => <Link to={docHref(apiId, docId)}>{docId}</Link>}
        />
      )}
      <Operations
        snap={snap}
        endpointLink={(apiId, docId, label) => <Link to={docHref(apiId, docId)}>{label}</Link>}
      />
      {maintainer ? <VerifiedMappings concept={snap.concept} /> : null}
      <div className={`model-cols${view === 'table' ? ' two-up' : ''}`}>
        <ShareCard snap={snap} />
        <ReviseCard snap={snap} />
        <Card className="pad">
          <h2 className="h2-sm">Open questions</h2>
          {snap.openQuestions.length === 0 ? (
            <p className="muted">No open questions.</p>
          ) : (
            <ul className="oq">
              {snap.openQuestions.map((q) => (
                <li key={q.question}>
                  <div>{richText(q.question)}</div>
                  {q.detail ? <div className="faint small">{q.detail}</div> : null}
                  {q.options?.length ? (
                    <div className="row oq-options" aria-label="Options">
                      {q.options.map((o) => (
                        <Chip key={o}>{o}</Chip>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="pad">
          <h2 className="h2-sm">Coverage</h2>
          <ul className="cov">
            {snap.inputs.map((a) => {
              const c = snap.coverage[a.id] ?? { mapped: 0, total: countLeaves(snap) };
              return (
                <li key={a.id}>
                  <span className="cov-name">
                    <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={26} />
                    <span className="cov-label">{a.shortName}</span>
                    <span className="mono small cov-count">
                      {c.mapped} of {c.total}
                    </span>
                  </span>
                  <span
                    className="cov-bar"
                    role="img"
                    aria-label={`${a.shortName}: ${c.mapped} of ${c.total} fields`}
                  >
                    <i
                      style={{
                        width: `${(c.mapped / Math.max(c.total, 1)) * 100}%`,
                        background: a.logo.color,
                      }}
                    />
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="faint small">
            Generated by Claude through Plume · prompt {snap.promptVersion}
          </p>
        </Card>
      </div>
    </>
  );
}
