import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type ModelSnapshot } from '@/api/types';
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
import { apiLabel } from '@/lib/names';
import { richText } from '@/lib/richText';
import { defaultSelection, type Selection } from './graph';
import { MappingGraph } from './MappingGraph';
import { docHref, MappingTable } from './MappingTable';
import {
  LineageHistory,
  LineageLine,
  OwnerKeyNotice,
  ReviewBanner,
  ReviseCard,
  ShareCard,
  VisibilityChip,
} from './ModelAccess';
import { StaleChip } from './StaleChip';

export function claudePrompt(s: ModelSnapshot): string {
  const apis = s.inputs.map((a) => a.shortName).join(', ');
  return (
    `Use the Plume connector. Call get_snapshot with id "${s.id}": the canonical ${s.name} model for ${apis}. ` +
    `It was generated and is unverified, so check each mapping with search_docs, get_endpoint and find_field ` +
    `before you write any mapping code.`
  );
}

function MappingDetail({ snap, sel }: { snap: ModelSnapshot; sel: Selection }) {
  const field = snap.fields.find((f) => f.name === sel.field);
  const api = snap.inputs.find((a) => a.id === sel.apiId);
  const src = field?.sources[sel.apiId];
  const support = field?.support[sel.apiId];
  if (!field || !api) return null;
  return (
    <>
      <div className="rowhead">
        <h2 className="mono-h">
          {field.name} ← {api.shortName}
        </h2>
        {support === 'derived' ? (
          <Chip tone="warn">
            derived: {src?.join?.length ? 'join' : src?.transform ? 'transform' : 'combine'}
          </Chip>
        ) : support === 'supported' ? (
          <Chip tone="ok">direct</Chip>
        ) : (
          <Chip>not supported</Chip>
        )}
      </div>
      {field.description ? <p className="muted small">{field.description}</p> : null}
      {!src ? (
        <p className="muted">{api.shortName} has no equivalent field.</p>
      ) : (
        <>
          {src.fetch ? (
            <div className="dl">
              <div className="dl-k">Fetch</div>
              <div className="mono">{src.fetch.endpoint}</div>
            </div>
          ) : null}
          <div className="dl">
            <div className="dl-k">Source</div>
            <div className="mono">{src.paths.map((p) => p.path).join(', ')}</div>
          </div>
          {src.transform ? (
            <div className="dl">
              <div className="dl-k">Transform</div>
              <div className="mono">{src.transform}</div>
            </div>
          ) : null}
          {src.join?.length ? (
            <div className="dl">
              <div className="dl-k">Join</div>
              {src.join.map((j) => (
                <div key={j} className="mono">
                  {j}
                </div>
              ))}
            </div>
          ) : null}
          {src.evidence?.map((e) => (
            <blockquote key={e.quote} className="evidence">
              <p>“{e.quote}”</p>
              <cite className="faint small">
                {e.docId ? <Link to={docHref(sel.apiId, e.docId)}>{e.docId}</Link> : null}
                {e.docId && e.anchor ? ' · ' : ''}
                {e.anchor}
              </cite>
            </blockquote>
          ))}
        </>
      )}
      {snap.citations.missing.length === 0 ? (
        <p className="cite ok">
          All {snap.citations.checked} cited paths found in the pinned builds
        </p>
      ) : (
        <p className="cite warn">
          {snap.citations.checked - snap.citations.found} of {snap.citations.checked} cited paths
          were not found and were dropped: {snap.citations.missing.join(', ')}
        </p>
      )}
    </>
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
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getSnapshot(snapshotId, signal),
    [client, snapshotId],
  );
  const { state, retry } = useAsync(load);
  const [picked, setPicked] = useState<Selection | null>(null);
  const [focusNonce, setFocusNonce] = useState(0);
  const [mapFilter, setMapFilter] = useState('');
  // null = the default for the model size (a big model opens as a table, with the graph focused on one field)
  const [viewChoice, setViewChoice] = useState<'table' | 'graph' | null>(null);
  const [scopeChoice, setScopeChoice] = useState<'field' | 'all' | null>(null);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');
  // right after someone without a token created this model: the owner key, shown once (then dropped from history)
  const location = useLocation();
  const navigate = useNavigate();
  const [ownerKey] = useState<string | null>(
    () => (location.state as { ownerKey?: string } | null)?.ownerKey ?? null,
  );
  const [ownerKeyOpen, setOwnerKeyOpen] = useState(ownerKey !== null);
  useEffect(() => {
    if (ownerKey) navigate(location.pathname, { replace: true, state: null });
    // once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const snap = state.status === 'ready' ? state.data : null;
  const selection = useMemo(() => picked ?? (snap ? defaultSelection(snap) : null), [picked, snap]);

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
  const options = snap.fields.flatMap((f) =>
    snap.inputs
      .filter((a) => f.support[a.id] && f.support[a.id] !== 'unsupported')
      .map((a) => ({ value: `${f.name}|${a.id}`, label: `${f.name} ← ${a.shortName}` })),
  );
  const big = snap.fields.length > BIG_MODEL;
  const view = viewChoice ?? (big ? 'table' : 'graph');
  const scope = scopeChoice ?? (big ? 'field' : 'all');
  const focusedField =
    scope === 'field' && selection
      ? snap.fields.find((f) => f.name === selection.field)
      : undefined;
  const graphSnap = focusedField
    ? {
        ...snap,
        fields: [focusedField],
        inputs: snap.inputs.filter(
          (a) => (focusedField.support[a.id] ?? 'unsupported') !== 'unsupported',
        ),
      }
    : snap;
  const filterText = mapFilter.trim().toLowerCase();
  const shownOptions = options.filter(
    (o) =>
      !filterText ||
      o.label.toLowerCase().includes(filterText) ||
      o.value === (selection ? `${selection.field}|${selection.apiId}` : ''),
  );

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{snap.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <VisibilityChip visibility={snap.visibility} />
            <Chip tone="warn">Generated, unverified</Chip>
            {snap.stale ? <StaleChip inputs={snap.staleInputs} /> : null}
            <Chip>{snap.inputs.length} APIs</Chip>
            <Chip>{snap.fields.length} fields</Chip>
            <Chip>snapshot {snap.id}</Chip>
          </div>
          <LineageLine snap={snap} />
        </div>
        <div className="row">
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
      {ownerKey && ownerKeyOpen ? (
        <div className="access-banner">
          <OwnerKeyNotice ownerKey={ownerKey} onClose={() => setOwnerKeyOpen(false)} />
        </div>
      ) : null}
      <div className="access-banner">
        <ReviewBanner snap={snap} onChanged={retry} />
        <LineageHistory snap={snap} />
      </div>
      {snap.stale ? (
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
          onChange={setViewChoice}
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
            onChange={setScopeChoice}
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
              ? 'Pick a field in the Mapping list below to see it here.'
              : 'Scroll to pan, Ctrl or ⌘ + scroll to zoom. Pick a mapping below to zoom to it.'}
        </span>
      </div>
      {view === 'table' ? (
        <MappingTable snapshot={snap} />
      ) : (scope === 'field' && !focusedField) || graphSnap.inputs.length === 0 ? (
        <p className="muted state">No API fills this field.</p>
      ) : (
        <MappingGraph
          key={`${scope}:${focusedField?.name ?? 'all'}`}
          snapshot={graphSnap}
          selection={selection}
          onSelect={setPicked}
          focusNonce={focusNonce}
          readable={big && scope === 'all'}
        />
      )}
      <div className={`model-cols${view === 'table' ? ' two-up' : ''}`}>
        {view === 'graph' ? (
          <Card className="pad">
            {options.length > 20 ? (
              <div className="map-filter">
                <label htmlFor="map-filter" className="sr-only">
                  Filter mappings
                </label>
                <input
                  id="map-filter"
                  type="search"
                  className="input"
                  placeholder={`Filter ${options.length} mappings by field or API`}
                  value={mapFilter}
                  onChange={(e) => setMapFilter(e.target.value)}
                />
                <p className="faint small" aria-live="polite">
                  {shownOptions.length} of {options.length} mappings
                </p>
              </div>
            ) : null}
            <label className="map-pick">
              <span className="sr-only">Mapping</span>
              <select
                className="input"
                value={selection ? `${selection.field}|${selection.apiId}` : ''}
                onChange={(e) => {
                  const [field = '', apiId = ''] = e.target.value.split('|');
                  setPicked({ field, apiId });
                  setFocusNonce((n) => n + 1); // a pick from the list also zooms the graph to it
                }}
              >
                {shownOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {selection ? <MappingDetail snap={snap} sel={selection} /> : null}
          </Card>
        ) : null}
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
              const c = snap.coverage[a.id] ?? { mapped: 0, total: snap.fields.length };
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
