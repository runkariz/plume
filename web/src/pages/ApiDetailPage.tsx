import { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import {
  ApiError,
  type ApiDetail,
  type ApiSummary,
  type BrowseResult,
  type ItemKind,
} from '@/api/types';
import {
  Card,
  Chip,
  Crumbs,
  EmptyState,
  ErrorState,
  Kv,
  LoadingState,
  Logo,
  MethodBadge,
  Metric,
  Segmented,
  Tile,
  RateLimitsCard,
} from '@/components';
import { DocsUpdatedBadge } from '@/components/DocsUpdatedBadge';
import { QualityBySource } from '@/components/QualityBySource';
import { SourcesLine } from '@/components/SourcesLine';
import { SearchIcon } from '@/icons';
import { breakable } from '@/lib/breakable';
import { operationOf, shownPath } from '@/lib/docHref';
import { ChangesTab } from './changes/ChangesTab';
import { docHref } from './models/MappingTable';
import { ModelList } from './models/ModelList';
import { AuthPanel } from './sections/AuthPanel';
import { EnvironmentsCard } from './sections/EnvironmentsCard';
import { McpPanel } from './sections/McpPanel';
import { TriggersPanel } from './sections/TriggersPanel';
import { categoryLabel, formatDate, formatScore, modelCount } from '@/lib/format';

type Tab = 'all' | ItemKind;
const TABS: { value: Tab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'endpoint', label: 'Endpoints' },
  { value: 'model', label: 'Models' },
  { value: 'guide', label: 'Guides' },
];

function Browse({ api }: { api: ApiSummary }) {
  const client = useApiClient();
  const [tab, setTab] = useState<Tab>('all');
  const [filter, setFilter] = useState('');
  const [debounced, setDebounced] = useState('');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(filter.trim()), 200);
    return () => clearTimeout(t);
  }, [filter]);

  const limit = showAll ? 500 : 9;
  const load = useCallback(
    (signal: AbortSignal): Promise<BrowseResult> =>
      client.browse(
        api.id,
        { kind: tab === 'all' ? undefined : tab, query: debounced || undefined, limit },
        signal,
      ),
    [client, api.id, tab, debounced, limit],
  );
  const { state, retry } = useAsync(load);

  return (
    <Card className="pad browse">
      <div className="rowhead">
        <h2>Browse</h2>
        <Segmented variant="pills" label="Kind" options={TABS} value={tab} onChange={setTab} />
      </div>
      <div className="searchbar">
        <SearchIcon aria-hidden />
        <input
          type="search"
          aria-label="Filter by path, method or resource"
          placeholder="Filter by path, method or resource"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      {state.status === 'loading' ? <LoadingState label="Loading items" /> : null}
      {state.status === 'error' ? (
        <ErrorState title="Could not load items" message={state.error.message} onRetry={retry} />
      ) : null}
      {state.status === 'ready' && state.data.items.length === 0 ? (
        <EmptyState title="Nothing matches">Try a different filter.</EmptyState>
      ) : null}
      {state.status === 'ready' && state.data.items.length > 0 ? (
        <>
          <ul className="ep-list">
            {state.data.items.map((it) => (
              <li key={it.id} className="ep">
                {it.method ? (
                  <MethodBadge method={it.method} />
                ) : (
                  <span className="kind-tag">{it.kind}</span>
                )}
                <div className="ep-main">
                  <div className={shownPath(it) ? 'mono ep-path' : 'ep-path'}>
                    {/* the whole row is clickable (stretched link); the link text names the item */}
                    <Link className="ep-link" to={docHref(api.id, it.id)}>
                      {shownPath(it) ? breakable(shownPath(it) ?? '') : it.title}
                    </Link>
                    {operationOf(it.id, it.method, it.path) ? (
                      <span className="faint small ep-op">
                        {' '}
                        · {operationOf(it.id, it.method, it.path)}
                      </span>
                    ) : null}
                  </div>
                  {shownPath(it) ? <div className="muted small">{it.title}</div> : null}
                </div>
                {it.resource ? <Chip>{it.resource}</Chip> : null}
              </li>
            ))}
          </ul>
          {!showAll && state.data.total > state.data.items.length ? (
            <div className="show-all">
              <button type="button" className="linkbtn" onClick={() => setShowAll(true)}>
                Show all {state.data.total}{' '}
                {tab === 'all' ? 'items' : TABS.find((t) => t.value === tab)?.label.toLowerCase()}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </Card>
  );
}

function Detail({ api }: { api: ApiDetail }) {
  const client = useApiClient();
  const [params, setParams] = useSearchParams();
  const raw = params.get('section');
  const loadMcp = useCallback(
    (signal: AbortSignal) => client.getMcp(api.id, signal),
    [client, api.id],
  );
  const { state: mcpState } = useAsync(loadMcp);
  // a Changes section exists only when the timeline has a build with notes: an older server (the route is missing) or
  // an API without notes shows no tab and no empty state
  const loadBuilds = useCallback(
    (signal: AbortSignal) => client.getChangesTimeline(api.id, signal),
    [client, api.id],
  );
  const { state: buildsState } = useAsync(loadBuilds);
  const builds = buildsState.status === 'ready' ? buildsState.data : [];
  const changes = builds.length > 0;
  // an MCP section exists only when the vendor runs an MCP server: otherwise no tab, no empty state
  const mcp =
    mcpState.status === 'ready' && mcpState.data.present && mcpState.data.servers.length > 0
      ? mcpState.data
      : null;
  const section: 'browse' | 'auth' | 'triggers' | 'mcp' | 'changes' =
    raw === 'auth' || raw === 'triggers' || (raw === 'mcp' && mcp) || (raw === 'changes' && changes)
      ? raw
      : 'browse';
  return (
    <>
      <div className="titlerow">
        <div className="title-left">
          <Logo text={api.logo.text} color={api.logo.color} url={api.logo.url} size={76} />
          <div>
            <h1 className="h1-sm">{api.name}</h1>
            <div className="row" style={{ gap: 8 }}>
              {api.isLive ? (
                <Chip tone="ok" dot>
                  Live
                </Chip>
              ) : api.status.kind === 'unpublished' ? (
                <Chip dot>Not published</Chip>
              ) : (
                <Chip tone="acc" dot>
                  Updating
                </Chip>
              )}
              <Chip tone="acc">{categoryLabel(api.category)}</Chip>
              <span className="muted">
                {api.docsAsOf
                  ? `${api.tag ? `${api.tag} · ` : ''}docs as of ${formatDate(api.docsAsOf)}`
                  : 'No docs published yet'}
              </span>
            </div>
            <SourcesLine sources={api.sources} extractedAt={api.extractedAt} />
            <DocsUpdatedBadge api={api.id} docsUpdated={api.docsUpdated} />
          </div>
        </div>
        <div className="row">
          {api.docLink ? (
            <a className="btn" href={api.docLink} target="_blank" rel="noreferrer">
              Official docs
            </a>
          ) : null}
          <a className="btn" href="#connect">
            Use in Claude Code
          </a>
          <Link className="btn primary" to={`/apis/${api.id}/try`}>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M7 4.5v15l12-7.5z" />
            </svg>
            Try it
          </Link>
        </div>
      </div>
      <div className="tiles">
        <Tile value={api.endpoints} label="Endpoints" />
        <Tile
          value={modelCount(api)}
          label="Models"
          hint={
            api.modelNames !== undefined && api.models !== api.modelNames
              ? `${api.models} model files${api.modelShapes ? ` · ${api.modelShapes} structures` : ''}`
              : undefined
          }
        />
        <Tile value={api.guides} label="Guides" />
        <Tile value={api.chunks} label="Searchable chunks" />
      </div>
      <div className="cols">
        <div className="stack">
          <Segmented
            label="Section"
            value={section}
            onChange={(v) => setParams(v === 'browse' ? {} : { section: v })}
            options={[
              { value: 'browse', label: 'Browse' },
              {
                value: 'auth',
                label: `Authentication${api.sections ? ` (${api.sections.auth})` : ''}`,
              },
              {
                value: 'triggers',
                label: `Triggers${api.sections ? ` (${api.sections.triggers})` : ''}`,
              },
              ...(changes ? [{ value: 'changes' as const, label: 'Changes' }] : []),
              ...(mcp ? [{ value: 'mcp' as const, label: `MCP (${mcp.servers.length})` }] : []),
            ]}
          />
          {section === 'auth' ? <AuthPanel apiId={api.id} /> : null}
          {section === 'triggers' ? <TriggersPanel apiId={api.id} /> : null}
          {section === 'mcp' && mcp ? <McpPanel mcp={mcp} /> : null}
          {section === 'changes' && changes ? <ChangesTab api={api.id} builds={builds} /> : null}
          {section === 'browse' ? <Browse api={api} /> : null}
        </div>
        <div className="stack">
          <Card className="pad">
            <h2 style={{ marginBottom: 12 }}>Answer quality</h2>
            {api.quality ? (
              <>
                <Metric label="Recall@5" value={formatScore(api.quality.recallAt5)} />
                <Metric label="MRR" value={formatScore(api.quality.mrr)} />
                {api.quality.inventedEndpoints !== null ? (
                  <Metric
                    label="Invented endpoints"
                    value={`${api.quality.inventedEndpoints} / ${api.quality.goldQuestions}`}
                    tone={api.quality.inventedEndpoints === 0 ? 'ok' : undefined}
                  />
                ) : null}
                {api.quality.citationHitRate !== undefined ? (
                  <Metric
                    label="Citation hit rate"
                    value={formatScore(api.quality.citationHitRate)}
                  />
                ) : null}
                {api.quality.factAccuracy !== undefined ? (
                  <Metric label="Fact accuracy" value={formatScore(api.quality.factAccuracy)} />
                ) : null}
                {api.quality.missingExpected ? (
                  <Metric label="Expected docs missing" value={api.quality.missingExpected} />
                ) : null}
                <QualityBySource rows={api.quality.bySource} />
                <p className="faint small" style={{ marginTop: 10 }}>
                  Gold set of {api.quality.goldQuestions} questions · evaluated{' '}
                  {formatDate(api.quality.evaluatedAt)}
                </p>
              </>
            ) : (
              <p className="muted">
                Not evaluated yet. Scores appear here once the quality gate has run on a build.
              </p>
            )}
          </Card>
          <Card className="pad">
            <h2 style={{ marginBottom: 12 }}>Index</h2>
            <Kv label="Embedding" value={api.index.embedding ?? '–'} />
            <Kv label="Dimensions" value={api.index.dimensions ?? '–'} />
            <Kv label="Store" value={api.index.store} />
            <Kv label="Build" value={api.index.build ?? '–'} mono />
          </Card>
          <RateLimitsCard limits={api.rateLimits} />
          <EnvironmentsCard apiId={api.id} />
          <ModelList api={api.id} title="Canonical models" />
          <Card className="pad" id="connect">
            <h2 style={{ marginBottom: 12 }}>Connect</h2>
            <pre className="code">
              <span className="c"># Claude Code</span>
              {'\n'}
              {api.connect.claudeCode}
            </pre>
          </Card>
        </div>
      </div>
    </>
  );
}

export function ApiDetailPage() {
  const { apiId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.getApi(apiId, signal), [client, apiId]);
  const { state, retry } = useAsync(load);

  const name = state.status === 'ready' ? state.data.name : 'API';
  return (
    <>
      <Crumbs items={[{ label: 'APIs', to: '/' }, { label: name }]} />
      {state.status === 'loading' ? <LoadingState label="Loading API" /> : null}
      {state.status === 'error' ? (
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'API not found'
              : 'Could not load this API'
          }
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {state.status === 'ready' ? <Detail api={state.data} /> : null}
      <div style={{ height: 48 }} />
    </>
  );
}
