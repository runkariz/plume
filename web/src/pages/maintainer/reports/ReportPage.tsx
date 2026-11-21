import { useCallback, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type Report, type ReportNote, type ReportStatus } from '@/api/types';
import { Button, Card, Chip, Crumbs, ErrorState, LoadingState } from '@/components';
import { formatDate, shortBuild } from '@/lib/format';
import {
  PUBLIC_REASON,
  REASON_MAX,
  STATUS_LABEL,
  STATUSES,
  shortSession,
  statusLabel,
  statusTone,
} from './labels';

/** What the reader said, in the server's redacted text: the markers ([token], [email] ...) are shown as they are. */
function Said({ label, text }: { label: string; text: string | null | undefined }) {
  if (!text?.trim()) return null;
  return (
    <div className="dl">
      <div className="dl-k">{label}</div>
      <p className="report-text">{text}</p>
    </div>
  );
}

function Note({ n }: { n: ReportNote }) {
  const session = shortSession(n.sessionHash);
  return (
    <li className="report-note">
      <div className="row" style={{ gap: 8 }}>
        <Chip tone={n.kind === 'duplicate' ? 'info' : 'neutral'}>
          {n.kind === 'duplicate' ? 'duplicate report' : n.kind}
        </Chip>
        <span className="faint small">
          {formatDate(n.createdAt)}
          {n.clientName ? <> · {n.clientName}</> : null}
          {session ? (
            <>
              {' '}
              · session <span className="mono">{session}</span>
            </>
          ) : null}
          {n.build ? <> · build {shortBuild(n.build)}</> : null}
          {n.redactions ? <> · {n.redactions} redacted</> : null}
        </span>
      </div>
      <p className="report-text">{n.text}</p>
    </li>
  );
}

/** The status of a report and the reason for it; the reasons of answered and out-of-scope reports are public. */
function StatusForm({ report, onSaved }: { report: Report; onSaved: (r: Report) => void }) {
  const client = useApiClient();
  const [status, setStatus] = useState<ReportStatus>(report.status);
  const [reason, setReason] = useState(report.reason ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const changed = status !== report.status || reason.trim() !== (report.reason ?? '').trim();
  const tooLong = reason.length > REASON_MAX;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || !changed || tooLong) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      onSaved(await client.setReportStatus(report.id, status, reason.trim() || null));
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label="Triage">
      <fieldset className="report-status">
        <legend className="h2-sm">Status</legend>
        <div className="row report-status-options">
          {STATUSES.map((s) => (
            <label key={s} className={`report-option${status === s ? ' on' : ''}`}>
              <input
                type="radio"
                name="status"
                value={s}
                checked={status === s}
                onChange={() => {
                  setStatus(s);
                  setSaved(false);
                }}
                className="sr-only"
              />
              {STATUS_LABEL[s]}
            </label>
          ))}
        </div>
      </fieldset>
      <label htmlFor="report-reason" className="h2-sm" style={{ display: 'block', marginTop: 14 }}>
        Reason
      </label>
      <textarea
        id="report-reason"
        className="input report-reason-input"
        rows={3}
        value={reason}
        onChange={(e) => {
          setReason(e.target.value);
          setSaved(false);
        }}
        aria-describedby="report-reason-help"
      />
      <p id="report-reason-help" className="faint small">
        {reason.length} / {REASON_MAX}
        {PUBLIC_REASON.includes(status) ? (
          <>
            {' '}
            · <b>Readers see this reason</b>: the reason of an answered or out-of-scope report is
            shown by find_reported_questions.
          </>
        ) : null}
      </p>
      {error ? (
        <p className="cite warn" role="alert">
          {error}
        </p>
      ) : null}
      <div className="row" style={{ marginTop: 10 }}>
        <Button variant="primary" type="submit" disabled={busy || !changed || tooLong}>
          {busy ? 'Saving…' : 'Save status'}
        </Button>
        {saved ? (
          <span role="status" className="small ok">
            Saved.
          </span>
        ) : null}
      </div>
    </form>
  );
}

/** One report with its notes and the triage form (maintainer). */
export function ReportPage() {
  const { reportId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getReport(reportId, signal),
    [client, reportId],
  );
  const { state, retry } = useAsync(load);
  // the report as the last save answered it, for this report only (the notes come from the read)
  const [saved, setSaved] = useState<Report | null>(null);
  const base = state.status === 'ready' ? state.data : null;
  const newer = saved && saved.id === reportId ? saved : null;
  const report: Report | null = base ? { ...base, ...(newer ?? {}), notes: base.notes } : null;

  const crumbs = [
    { label: 'Maintainer', to: '/maintainer' },
    { label: 'Reported questions', to: '/maintainer/reports' },
    { label: report ? report.id : reportId },
  ];
  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the report" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Report not found'
              : 'Could not load the report'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  if (!report) return null;
  const session = shortSession(report.sessionHash);
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm report-title">{report.question}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <Chip tone={statusTone(report.status)}>{statusLabel(report.status)}</Chip>
            <Chip tone={report.reportCount > 1 ? 'acc' : 'neutral'}>
              {report.reportCount} report{report.reportCount === 1 ? '' : 's'}
            </Chip>
            <span className="faint small mono">{report.id}</span>
          </div>
        </div>
        <Link className="btn" to="/maintainer/reports">
          Back to the reports
        </Link>
      </div>

      <Card className="pad" role="region" aria-label="The report">
        <h2 className="h2-sm">What was reported</h2>
        <p className="faint small">
          <span className="mono">{report.api}</span>
          {report.build ? <> · build {shortBuild(report.build)}</> : null}
          {report.clientName ? <> · {report.clientName}</> : null}
          {session ? (
            <>
              {' '}
              · session <span className="mono">{session}</span>
            </>
          ) : null}{' '}
          · first reported {formatDate(report.createdAt)} · updated {formatDate(report.updatedAt)}
          {report.redactions ? <> · {report.redactions} redacted</> : null}
        </p>
        <Said label="Question" text={report.question} />
        <Said label="What was tried" text={report.whatWasTried} />
        <Said label="What was missing" text={report.whatWasMissing} />
        <p className="faint small">
          Text is redacted by the server: markers such as [token], [email] or [number] stand for
          what it removed.
        </p>
      </Card>

      <Card className="pad" role="region" aria-label="Triage">
        <StatusForm key={report.id} report={report} onSaved={setSaved} />
      </Card>

      <Card className="pad" role="region" aria-label="Notes">
        <h2 className="h2-sm">
          Notes <span className="faint small">({report.notes?.length ?? 0})</span>
        </h2>
        {report.notes?.length ? (
          <ul className="plain report-notes" aria-label="Notes on this report">
            {report.notes.map((n) => (
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
