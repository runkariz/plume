import { useCallback, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import {
  ApiError,
  type MappingReport,
  type MappingReportAction,
  type MappingRoute,
} from '@/api/types';
import { Button, Card, Chip, Crumbs, ErrorState, LoadingState } from '@/components';
import { formatDate, shortBuild } from '@/lib/format';
import { REASON_MAX, shortSession } from './labels';
import {
  KIND_LABEL,
  ROUTES,
  ROUTE_LABEL,
  kindLabel,
  mappingStatusLabel,
  mappingStatusTone,
  routeShort,
} from './mappingLabels';
import { ConsentChip } from './consent';
import { Citation } from './QuoteInDoc';
import { ReportsTabs } from './ReportsTabs';

/** A note the server redacted: the markers stay. */
function Note({ n }: { n: NonNullable<MappingReport['notes']>[number] }) {
  const session = shortSession(n.sessionHash);
  return (
    <li className="report-note">
      <div className="row" style={{ gap: 8 }}>
        <Chip tone={n.kind === 'duplicate' ? 'info' : 'neutral'}>
          {n.kind === 'duplicate' ? 'duplicate report' : n.kind}
        </Chip>
        <ConsentChip method={n.consentMethod} />
        <span className="faint small">
          {formatDate(n.createdAt)}
          {n.clientName ? <> · {n.clientName}</> : null}
          {session ? (
            <>
              {' '}
              · session <span className="mono">{session}</span>
            </>
          ) : null}
          {n.redactions ? <> · {n.redactions} redacted</> : null}
        </span>
      </div>
      <p className="report-text">{n.text}</p>
    </li>
  );
}

/** A verified absence: the field is not available on the API, and what it must not be mapped from. */
export function Absence({ api, notFrom }: { api: string; notFrom?: string[] }) {
  const from = (notFrom ?? []).filter(Boolean);
  return (
    <>
      <p className="map-absence">
        <b>Not available on {api}</b>
      </p>
      {from.length ? (
        <div className="dl">
          <div className="dl-k">Not from</div>
          <div className="mono">{from.join(', ')}</div>
        </div>
      ) : null}
    </>
  );
}

/** The current mapping as the reader's LLM described it, beside the one it suggests (kept only when it validated). */
function Compare({ r }: { r: MappingReport }) {
  const s = r.suggestion;
  return (
    <div className="map-compare">
      <section aria-label="Current mapping">
        <h3 className="map-col-title">Current mapping</h3>
        {r.currentMapping?.trim() ? (
          <p className="report-text">{r.currentMapping}</p>
        ) : (
          <p className="muted">The field has no mapping, the report says.</p>
        )}
        <p className="faint small">As the reader&apos;s LLM described it, in words.</p>
      </section>
      <section aria-label="Suggested mapping">
        <h3 className="map-col-title">Suggested mapping</h3>
        {s?.notAvailable ? (
          <Absence api={r.api} notFrom={s.notFrom} />
        ) : s ? (
          <>
            <div className="dl">
              <div className="dl-k">Source</div>
              <div className="mono">{s.paths.join(', ')}</div>
            </div>
            {s.fetch ? (
              <div className="dl">
                <div className="dl-k">Fetch</div>
                <div className="mono">{s.fetch}</div>
              </div>
            ) : null}
          </>
        ) : r.validation && !r.validation.ok ? (
          <p className="muted">
            Not kept: the suggestion failed the validator, so only the problem is stored.
          </p>
        ) : (
          <p className="muted">No suggestion was given.</p>
        )}
      </section>
    </div>
  );
}

function Validator({ r }: { r: MappingReport }) {
  if (!r.validation) return null;
  return (
    <div className="map-validator" role="group" aria-label="Validator result">
      <div className="row" style={{ gap: 8 }}>
        <Chip tone={r.validation.ok ? 'ok' : 'bad'}>
          {r.validation.ok ? 'Passed the validator' : 'Failed the validator'}
        </Chip>
        <span className="faint small">
          The same validator as a model draft: the field must be in the API&apos;s package and the
          quote in the cited document.
        </span>
      </div>
      {r.validation.reason ? <p className="mono small map-reason">{r.validation.reason}</p> : null}
      {!r.validation.ok ? (
        <p className="small muted">
          Plume never stores an unproven mapping as a suggestion; it can only be accepted if it
          passes.
        </p>
      ) : null}
    </div>
  );
}

/** Accept, reject, route or reopen, with a reason. The server refuses an accept without a valid suggestion. */
function Actions({ r, onDone }: { r: MappingReport; onDone: (r: MappingReport) => void }) {
  const client = useApiClient();
  const [reason, setReason] = useState('');
  const [route, setRoute] = useState<MappingRoute>('plume');
  const [busy, setBusy] = useState<MappingReportAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const trimmed = reason.trim();
  const tooLong = reason.length > REASON_MAX;
  const canAccept = r.validation?.ok === true && r.status !== 'accepted';

  async function act(action: MappingReportAction, e?: FormEvent) {
    e?.preventDefault();
    if (busy || tooLong) return;
    setBusy(action);
    setError(null);
    setDone(null);
    try {
      const next = await client.actOnMappingReport(r.id, {
        action,
        reason: trimmed || undefined,
        route: action === 'route' ? route : undefined,
      });
      onDone(next);
      setDone(
        action === 'accept'
          ? 'Accepted: it is now a verified mapping.'
          : action === 'reject'
            ? 'Rejected.'
            : action === 'route'
              ? `Routed to ${routeShort(route)}.`
              : 'Reopened.',
      );
      setReason('');
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? `The server refused it: ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Could not save',
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <form onSubmit={(e) => e.preventDefault()} aria-label="Decide">
      <h2 className="h2-sm">Decide</h2>
      <label htmlFor="mreport-reason" className="small" style={{ display: 'block', marginTop: 8 }}>
        Reason
      </label>
      <textarea
        id="mreport-reason"
        className="input report-reason-input"
        rows={3}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        aria-describedby="mreport-reason-help"
      />
      <p id="mreport-reason-help" className="faint small">
        {reason.length} / {REASON_MAX} · A reason is needed to accept, reject or route.{' '}
        <b>Readers see the reason of a rejected report</b> when they look for similar reports.
      </p>
      {error ? (
        <p className="cite warn" role="alert">
          {error}
        </p>
      ) : null}
      <div className="row map-actions">
        <Button
          variant="primary"
          type="button"
          disabled={!canAccept || !trimmed || busy !== null || tooLong}
          onClick={() => void act('accept')}
        >
          {busy === 'accept' ? 'Accepting…' : 'Accept'}
        </Button>
        <Button
          type="button"
          disabled={r.status === 'rejected' || !trimmed || busy !== null || tooLong}
          onClick={() => void act('reject')}
        >
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
        <span className="row map-route">
          <label htmlFor="mreport-route" className="sr-only">
            Route to
          </label>
          <select
            id="mreport-route"
            className="input"
            value={route}
            onChange={(e) => setRoute(e.target.value as MappingRoute)}
          >
            {ROUTES.map((x) => (
              <option key={x} value={x}>
                {ROUTE_LABEL[x]}
              </option>
            ))}
          </select>
          <Button
            type="button"
            disabled={!trimmed || busy !== null || tooLong}
            onClick={() => void act('route')}
          >
            {busy === 'route' ? 'Routing…' : 'Route'}
          </Button>
        </span>
        {r.status !== 'open' ? (
          <Button type="button" disabled={busy !== null} onClick={() => void act('reopen')}>
            {busy === 'reopen' ? 'Reopening…' : 'Reopen'}
          </Button>
        ) : null}
      </div>
      {!canAccept && r.status !== 'accepted' ? (
        <p className="faint small">
          Accept needs a suggestion that passed the validator; this report has none.
        </p>
      ) : null}
      {canAccept ? (
        <p className="faint small">
          Accepting makes the suggestion a verified mapping, shown first in sessions on this API as
          &quot;verified (user report {r.id})&quot; and re-validated on every new build.
        </p>
      ) : null}
      {done ? (
        <p role="status" className="small ok">
          {done}
        </p>
      ) : null}
    </form>
  );
}

/** One mapping report: the problem, current against suggested, the citations with the quote marked, the validator, the decision. */
export function MappingReportPage() {
  const { reportId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getMappingReport(reportId, signal),
    [client, reportId],
  );
  const { state, retry } = useAsync(load);
  const [saved, setSaved] = useState<MappingReport | null>(null);
  const base = state.status === 'ready' ? state.data : null;
  const newer = saved && saved.id === reportId ? saved : null;
  const r: MappingReport | null = base ? { ...base, ...(newer ?? {}), notes: base.notes } : null;

  const crumbs = [
    { label: 'Maintainer', to: '/maintainer' },
    { label: 'Mapping reports', to: '/maintainer/mapping-reports' },
    { label: r ? r.id : reportId },
  ];
  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the mapping report" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Mapping report not found'
              : 'Could not load the mapping report'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  if (!r) return null;
  const session = shortSession(r.sessionHash);
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm report-title">
            <span className="mono">{r.conceptName ?? r.concept}</span> ›{' '}
            <span className="mono">{r.canonicalField}</span>
          </h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <Chip tone={mappingStatusTone(r.status)}>
              {mappingStatusLabel(r.status)}
              {r.status === 'routed' && r.route ? `: ${routeShort(r.route)}` : ''}
            </Chip>
            <Chip>{kindLabel(r.kind)}</Chip>
            <Chip tone={r.reportCount > 1 ? 'acc' : 'neutral'}>
              {r.reportCount} report{r.reportCount === 1 ? '' : 's'}
            </Chip>
            <ConsentChip method={r.consentMethod} />
            <span className="faint small mono">{r.id}</span>
          </div>
        </div>
        <Link className="btn" to="/maintainer/mapping-reports">
          Back to the mapping reports
        </Link>
      </div>
      <ReportsTabs />

      <Card className="pad" role="region" aria-label="The report">
        <h2 className="h2-sm">What was reported</h2>
        <p className="faint small">
          <span className="mono">{r.api}</span>
          {r.build ? <> · build {shortBuild(r.build)}</> : null}
          {r.concept !== (r.conceptName ?? r.concept) ? (
            <>
              {' '}
              · concept <span className="mono">{r.concept}</span>
            </>
          ) : null}
          {r.modelId ? (
            <>
              {' '}
              · model <Link to={`/models/${encodeURIComponent(r.modelId)}`}>{r.modelId}</Link>
            </>
          ) : (
            <> · reported from a session</>
          )}
          {r.clientName ? <> · {r.clientName}</> : null}
          {session ? (
            <>
              {' '}
              · session <span className="mono">{session}</span>
            </>
          ) : null}{' '}
          · first reported {formatDate(r.createdAt)} · updated {formatDate(r.updatedAt)}
          {r.redactions ? <> · {r.redactions} redacted</> : null}
        </p>
        <div className="dl">
          <div className="dl-k">{KIND_LABEL[r.kind] ?? r.kind}</div>
          <p className="report-text">{r.problem}</p>
        </div>
        {r.reason ? (
          <div className="dl">
            <div className="dl-k">Maintainer&apos;s reason</div>
            <p className="report-text">{r.reason}</p>
          </div>
        ) : null}
      </Card>

      <Card className="pad" role="region" aria-label="Current and suggested mapping">
        <h2 className="h2-sm">Current and suggested mapping</h2>
        <Compare r={r} />
        {r.suggestion?.evidence?.length ? (
          <div className="map-evidence" role="group" aria-label="Citations of the suggestion">
            <h3 className="map-col-title">Citations</h3>
            {r.suggestion.evidence.map((e, i) => (
              <Citation key={`${e.docId}-${i}`} api={r.api} e={e} />
            ))}
          </div>
        ) : null}
        <Validator r={r} />
      </Card>

      {r.verified ? (
        <Card className="pad" role="region" aria-label="Verified mapping">
          <h2 className="h2-sm">Verified mapping</h2>
          <div className="row" style={{ gap: 8 }}>
            <Chip tone={r.verified.suspended ? 'warn' : 'ok'}>
              {r.verified.suspended ? 'Suspended' : 'Active'}
            </Chip>
            <span className="mono small">{r.verified.id}</span>
            <span className="faint small">
              verified (user report {r.id})
              {r.verified.build ? <> · validated on build {shortBuild(r.verified.build)}</> : null}
              {r.verified.validatedAt ? <> · {formatDate(r.verified.validatedAt)}</> : null}
            </span>
          </div>
          {r.verified.suspended ? (
            <p className="cite warn" role="note">
              Suspended:{' '}
              {r.verified.suspendedReason ?? 'a new build dropped the field or the quote'}. The
              report is reopened.
            </p>
          ) : null}
        </Card>
      ) : null}

      <Card className="pad" role="region" aria-label="Decision">
        <Actions key={r.id} r={r} onDone={(next) => setSaved(next)} />
      </Card>

      <Card className="pad" role="region" aria-label="Notes">
        <h2 className="h2-sm">
          Notes <span className="faint small">({r.notes?.length ?? 0})</span>
        </h2>
        {r.notes?.length ? (
          <ul className="plain report-notes" aria-label="Notes on this report">
            {r.notes.map((n) => (
              <Note key={n.id} n={n} />
            ))}
          </ul>
        ) : (
          <p className="muted">No notes: nobody added to this report.</p>
        )}
      </Card>
      <div style={{ height: 40 }} />
    </>
  );
}
