import { useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { Report, ReportStatus } from '@/api/types';
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
import { ConsentChip, CONSENT_FILTERS, isConsentFilter, matchesConsent } from './consent';
import { ReportsTabs } from './ReportsTabs';
import { STATUS_LABEL, STATUSES, shortSession, statusLabel, statusTone } from './labels';

type Filter = ReportStatus | 'all';

const OPTIONS = [
  { value: 'all' as Filter, label: 'All' },
  ...STATUSES.map((s) => ({ value: s as Filter, label: STATUS_LABEL[s] })),
];

const isStatus = (v: string | null): v is ReportStatus => STATUSES.includes(v as ReportStatus);

/** One report in the list: the question, how often it was reported and where it stands. */
function ReportRow({ r }: { r: Report }) {
  const session = shortSession(r.sessionHash);
  return (
    <li className="report-row">
      <div className="report-main">
        <Link className="report-question" to={`/maintainer/reports/${encodeURIComponent(r.id)}`}>
          {r.question}
        </Link>
        <div className="faint small report-meta">
          <span className="mono">{r.api}</span>
          {r.build ? <> · build {shortBuild(r.build)}</> : null}
          {r.clientName ? <> · {r.clientName}</> : null}
          {session ? (
            <>
              {' '}
              · session <span className="mono">{session}</span>
            </>
          ) : null}{' '}
          · updated {formatDate(r.updatedAt)}
        </div>
        {r.reason ? <p className="small muted report-reason">{r.reason}</p> : null}
      </div>
      <div className="row report-chips">
        <Chip tone={r.reportCount > 1 ? 'acc' : 'neutral'}>
          {r.reportCount} report{r.reportCount === 1 ? '' : 's'}
        </Chip>
        <Chip tone={statusTone(r.status)}>{statusLabel(r.status)}</Chip>
        <ConsentChip method={r.consentMethod} />
      </div>
    </li>
  );
}

/**
 * The questions readers' LLMs reported (maintainer): most reported first, filtered by API and status in the URL. The text
 * is the server's, already redacted (markers like [token] stay), and is shown as plain text.
 */
export function ReportsPage() {
  const client = useApiClient();
  const [params, setParams] = useSearchParams();
  const api = params.get('api') ?? '';
  const statusParam = params.get('status');
  const status: Filter = isStatus(statusParam) ? statusParam : 'all';
  const consentParam = params.get('consent');
  const consent = isConsentFilter(consentParam) ? consentParam : 'all';

  const loadApis = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state: apis } = useAsync(loadApis);
  const load = useCallback(
    (signal: AbortSignal) =>
      client.listReports(
        { api: api || undefined, status: status === 'all' ? undefined : status },
        signal,
      ),
    [client, api, status],
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

  // the server has no consent filter: it is applied to the list it sent
  const reports =
    state.status === 'ready' ? state.data.reports.filter((r) => matchesConsent(r, consent)) : null;
  // reporting is off on this server: reports made earlier are still listed and can be triaged
  const off = state.status === 'ready' && state.data.enabled === false;
  return (
    <>
      <Crumbs
        items={[{ label: 'Maintainer', to: '/maintainer' }, { label: 'Reported questions' }]}
      />
      <div className="titlerow">
        <h1 className="h1-sm">Reported questions</h1>
      </div>
      <ReportsTabs />
      <p className="muted">
        What readers&apos; LLMs reported when Plume did not give them what they needed. The text is
        redacted by the server; most reported first.
      </p>
      <div className="row report-filters">
        <label className="sr-only" htmlFor="reports-api">
          API
        </label>
        <select
          id="reports-api"
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
        <label className="sr-only" htmlFor="reports-consent">
          Consent
        </label>
        <select
          id="reports-consent"
          className="input"
          value={consent}
          onChange={(e) => set('consent', e.target.value === 'all' ? '' : e.target.value)}
        >
          {CONSENT_FILTERS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <Segmented
          variant="pills"
          label="Status"
          options={OPTIONS}
          value={status}
          onChange={(v) => set('status', v === 'all' ? '' : v)}
        />
      </div>
      {state.status === 'loading' ? <LoadingState label="Loading the reports" /> : null}
      {off ? (
        <Banner tone="accent" title="Reported questions are off on this server">
          Readers cannot report questions (PLUME_REPORTS is off). Reports made earlier are listed
          below, and you can still triage them.
        </Banner>
      ) : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not load the reports"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {reports && reports.length === 0 ? (
        <EmptyState title="No reports">
          {api || status !== 'all' || consent !== 'all'
            ? 'No report matches this filter.'
            : 'Nothing has been reported yet.'}
        </EmptyState>
      ) : null}
      {reports && reports.length > 0 ? (
        <Card className="pad">
          <p className="faint small" aria-live="polite">
            {reports.length} report{reports.length === 1 ? '' : 's'}
          </p>
          <ul className="plain report-list" aria-label="Reports">
            {reports.map((r) => (
              <ReportRow key={r.id} r={r} />
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
