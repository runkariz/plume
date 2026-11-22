import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { MappingReport, MappingReportKind, MappingReportStatus } from '@/api/types';
import {
  Banner,
  Card,
  Chip,
  Crumbs,
  EmptyState,
  ErrorState,
  LoadingState,
  Segmented,
} from '@/components';
import { formatDate, shortBuild } from '@/lib/format';
import {
  KIND_LABEL,
  MAPPING_KINDS,
  MAPPING_STATUSES,
  MAPPING_STATUS_LABEL,
  kindLabel,
  mappingStatusLabel,
  mappingStatusTone,
  routeShort,
} from './mappingLabels';
import { ReportsTabs } from './ReportsTabs';

type StatusFilter = MappingReportStatus | 'all';

const STATUS_OPTIONS = [
  { value: 'all' as StatusFilter, label: 'All' },
  ...MAPPING_STATUSES.map((s) => ({ value: s as StatusFilter, label: MAPPING_STATUS_LABEL[s] })),
];

const isStatus = (v: string | null): v is MappingReportStatus =>
  MAPPING_STATUSES.includes(v as MappingReportStatus);
const isKind = (v: string | null): v is MappingReportKind =>
  MAPPING_KINDS.includes(v as MappingReportKind);

/** What the suggestion came to: it passed the validator, failed it (and was not kept), or there was none. */
function SuggestionChip({ r }: { r: MappingReport }) {
  if (!r.validation) return <Chip>no suggestion</Chip>;
  return r.validation.ok ? (
    <Chip tone="ok">suggestion valid</Chip>
  ) : (
    <Chip tone="bad">suggestion failed</Chip>
  );
}

function Row({ r }: { r: MappingReport }) {
  return (
    <li className="report-row">
      <div className="report-main">
        <Link
          className="report-question"
          to={`/maintainer/mapping-reports/${encodeURIComponent(r.id)}`}
        >
          <span className="mono">{r.conceptName ?? r.concept}</span> ›{' '}
          <span className="mono">{r.canonicalField}</span>
        </Link>
        <p className="small report-problem">{r.problem}</p>
        <div className="faint small report-meta">
          <span className="mono">{r.api}</span>
          {r.build ? <> · build {shortBuild(r.build)}</> : null}
          {r.clientName ? <> · {r.clientName}</> : null} · updated {formatDate(r.updatedAt)}
        </div>
        {r.reason ? <p className="small muted report-reason">{r.reason}</p> : null}
      </div>
      <div className="row report-chips">
        <Chip tone={r.reportCount > 1 ? 'acc' : 'neutral'}>
          {r.reportCount} report{r.reportCount === 1 ? '' : 's'}
        </Chip>
        <Chip>{kindLabel(r.kind)}</Chip>
        <SuggestionChip r={r} />
        {r.verified ? (
          <Chip tone={r.verified.suspended ? 'warn' : 'ok'}>
            {r.verified.suspended ? 'verified, suspended' : 'verified'}
          </Chip>
        ) : null}
        <Chip tone={mappingStatusTone(r.status)}>
          {mappingStatusLabel(r.status)}
          {r.status === 'routed' && r.route ? `: ${routeShort(r.route)}` : ''}
        </Chip>
      </div>
    </li>
  );
}

/**
 * The mappings readers' LLMs reported as wrong or missing (maintainer): per concept, field and API, most reported
 * first. Filters by API, concept, status and kind are kept in the URL. Text is the server's redacted text, as plain text.
 */
export function MappingReportsPage() {
  const client = useApiClient();
  const [params, setParams] = useSearchParams();
  const api = params.get('api') ?? '';
  const concept = params.get('concept') ?? '';
  const statusParam = params.get('status');
  const kindParam = params.get('kind');
  const status: StatusFilter = isStatus(statusParam) ? statusParam : 'all';
  const kind = isKind(kindParam) ? kindParam : '';
  const [conceptText, setConceptText] = useState(concept);

  const loadApis = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state: apis } = useAsync(loadApis);
  const load = useCallback(
    (signal: AbortSignal) =>
      client.listMappingReports(
        {
          api: api || undefined,
          concept: concept || undefined,
          status: status === 'all' ? undefined : status,
          kind: kind || undefined,
        },
        signal,
      ),
    [client, api, concept, status, kind],
  );
  const { state, retry } = useAsync(load);

  const set = (key: string, value: string) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  const reports = state.status === 'ready' ? state.data.reports : null;
  const off = state.status === 'ready' && state.data.enabled === false;

  function applyConcept() {
    set('concept', conceptText.trim());
  }

  return (
    <>
      <Crumbs items={[{ label: 'Maintainer', to: '/maintainer' }, { label: 'Mapping reports' }]} />
      <div className="titlerow">
        <h1 className="h1-sm">Mapping reports</h1>
      </div>
      <ReportsTabs />
      <p className="muted">
        Mappings of canonical models that readers&apos; LLMs reported as wrong or missing. A
        suggestion is kept only when it passed the same validator as a model draft; most reported
        first.
      </p>
      <div className="row report-filters">
        <label className="sr-only" htmlFor="mreports-api">
          API
        </label>
        <select
          id="mreports-api"
          className="input"
          value={api}
          onChange={(e) => set('api', e.target.value)}
        >
          <option value="">All APIs</option>
          {apis.status === 'ready'
            ? apis.data.items.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))
            : null}
        </select>
        <label className="sr-only" htmlFor="mreports-kind">
          Kind
        </label>
        <select
          id="mreports-kind"
          className="input"
          value={kind}
          onChange={(e) => set('kind', e.target.value)}
        >
          <option value="">All kinds</option>
          {MAPPING_KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
        <div role="search" className="row" style={{ gap: 6 }}>
          <label className="sr-only" htmlFor="mreports-concept">
            Concept
          </label>
          <input
            id="mreports-concept"
            className="input"
            placeholder="Concept, e.g. inventory/stock"
            value={conceptText}
            onChange={(e) => setConceptText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyConcept();
            }}
          />
          <button type="button" className="btn" onClick={applyConcept}>
            Filter
          </button>
        </div>
        <Segmented
          variant="pills"
          label="Status"
          options={STATUS_OPTIONS}
          value={status}
          onChange={(v) => set('status', v === 'all' ? '' : v)}
        />
      </div>
      {state.status === 'loading' ? <LoadingState label="Loading the mapping reports" /> : null}
      {off ? (
        <Banner tone="accent" title="Reports are off on this server">
          Readers cannot report mappings (PLUME_REPORTS is off). Reports made earlier are listed
          below, and you can still triage them.
        </Banner>
      ) : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not load the mapping reports"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {reports && reports.length === 0 ? (
        <EmptyState title="No mapping reports">
          {api || concept || kind || status !== 'all'
            ? 'No report matches this filter.'
            : 'No mapping has been reported yet.'}
        </EmptyState>
      ) : null}
      {reports && reports.length > 0 ? (
        <Card className="pad">
          <p className="faint small" aria-live="polite">
            {reports.length} report{reports.length === 1 ? '' : 's'}
          </p>
          <ul className="plain report-list" aria-label="Mapping reports">
            {reports.map((r) => (
              <Row key={r.id} r={r} />
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
