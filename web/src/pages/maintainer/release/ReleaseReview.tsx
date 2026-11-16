import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type ReleaseNotes } from '@/api/types';
import { Banner, Button, Card, Chip, Crumbs, ErrorState, Kv, LoadingState } from '@/components';
import { formatClock, formatDate, shortBuild } from '@/lib/format';
import { ChangeRow } from './ChangeRow';
import { DECISION_LABEL, REVIEW_LABEL } from './notes';

const REVIEW_TONE = { pending: 'warn', kept: 'ok', rolled_back: 'bad' } as const;
const SHOWN = 50;

/** The server's own reason for a refusal, in the maintainer's words. */
function refusal(e: unknown, what: string): string {
  if (e instanceof ApiError && e.status === 409) return `${what} is not possible now: ${e.message}`;
  if (e instanceof ApiError && e.status === 422) return e.message || 'The reason is required.';
  if (e instanceof ApiError && e.status === 401)
    return 'Your session is not valid any more. Sign in again.';
  return e instanceof Error && e.message ? e.message : `${what} failed.`;
}

/**
 * The maintainer's review of a build after it was published (`/maintainer/apis/:api/builds/:build/notes`). Nothing
 * is held: the build is live. The maintainer sees whether it needs attention, the extraction report (what the docs
 * did NOT change but the extractor did, by rule, with the server's explanation), and can keep the build, roll it
 * back (one click, with a reason: `latest` moves to the previous build) or roll it forward again, copy the issues
 * for stream, and promote a suspect change to confirmed with a verified quote. Suspect and unknown changes appear
 * only here, never on a public page.
 */
export function ReleaseReview() {
  const { apiId = '', buildId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getReleaseNotes(apiId, buildId, signal),
    [client, apiId, buildId],
  );
  const { state, retry } = useAsync(load);
  const [busy, setBusy] = useState<'keep' | 'rollback' | 'copy' | 'download' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState('');
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');
  const [moved, setMoved] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  const crumbs = [
    { label: 'Maintainer', to: '/maintainer' },
    { label: apiId, to: `/maintainer/apis/${apiId}/builds` },
    { label: shortBuild(buildId) },
  ];
  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the release notes" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        {state.error instanceof ApiError && state.error.status === 404 ? (
          <ErrorState
            title="No release notes for this build"
            message="The first build of an API has none (nothing to compare it with), and neither has a build loaded before notes existed."
            onRetry={retry}
          />
        ) : (
          <ErrorState
            title="Could not load the release notes"
            message={state.error.message}
            onRetry={retry}
          />
        )}
      </>
    );

  const n: ReleaseNotes = state.data;
  const decided = n.review !== 'pending';
  const canRollBack = n.tagged && Boolean(n.from) && n.review !== 'rolled_back';
  const canRollForward = n.review === 'rolled_back';
  const canKeep = n.review === 'pending';
  const items = n.items ?? [];

  async function keep() {
    setBusy('keep');
    setError(null);
    try {
      await client.keepRelease(apiId, buildId, note.trim() || undefined);
      setNote('');
      setMoved(canRollForward ? 'Rolled forward: this build is `latest` again.' : null);
      retry();
    } catch (e) {
      setError(refusal(e, canRollForward ? 'Rolling forward' : 'Keeping the build'));
    } finally {
      setBusy(null);
    }
  }

  async function rollBack() {
    if (reason.trim() === '') return;
    setBusy('rollback');
    setError(null);
    try {
      const r = await client.rollbackRelease(apiId, buildId, reason.trim());
      setMoved(
        `Rolled back: \`${r.tag}\` is ${shortBuild(r.buildId)} again. ${shortBuild(r.previous)} stays loaded and untagged.`,
      );
      setConfirm(false);
      setReason('');
      retry();
    } catch (e) {
      setError(refusal(e, 'Rolling back'));
    } finally {
      setBusy(null);
    }
  }

  async function issues(): Promise<string | null> {
    try {
      return await client.getReleaseIssues(apiId, buildId, 'markdown');
    } catch (e) {
      setError(refusal(e, 'Building the issues text'));
      return null;
    }
  }

  async function copyIssues() {
    setBusy('copy');
    setError(null);
    const text = await issues();
    if (text !== null) {
      try {
        await navigator.clipboard.writeText(text);
        setCopied('ok');
      } catch {
        setCopied('fail');
      }
      setTimeout(() => setCopied('idle'), 3000);
    }
    setBusy(null);
  }

  async function downloadIssues() {
    setBusy('download');
    setError(null);
    const text = await issues();
    if (text !== null) {
      const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${apiId}-${buildId}-issues.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    }
    setBusy(null);
  }

  const c = n.counts;
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">Release review: {apiId}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <span className="mono small" title={buildId}>
              {shortBuild(buildId)}
            </span>
            {n.tagged ? <Chip tone="acc">Latest</Chip> : <Chip>Not latest</Chip>}
            <Chip tone={REVIEW_TONE[n.review]}>{REVIEW_LABEL[n.review]}</Chip>
            {n.needsAttention ? <Chip tone="warn">Needs attention</Chip> : null}
          </div>
        </div>
        <Link className="btn" to={`/maintainer/apis/${apiId}/builds`}>
          All builds
        </Link>
      </div>

      {n.needsAttention ? (
        <Banner tone="warn" title="Needs attention">
          {n.attentionReason ? `${n.attentionReason}. ` : ''}
          Nothing is held: this build{n.tagged ? ' is live' : ' was loaded'}. Check the suspect
          changes below, and roll it back if it is wrong.
        </Banner>
      ) : null}
      {moved ? (
        <Banner tone="ok" title="Done">
          {moved}
        </Banner>
      ) : null}

      <div className="two">
        <Card className="pad" role="region" aria-label="What changed">
          <h2 className="h2-sm">What changed</h2>
          <ul className="plain notes-counts">
            <li>
              <b>{c.confirmed}</b> confirmed in the docs
            </li>
            <li>
              <b>{c.likely}</b> likely (vendor changelog)
            </li>
            <li>
              <b>{c.suspect ?? 0}</b> suspect: extraction artifacts
            </li>
            <li>
              <b>{c.unknown ?? 0}</b> without source evidence
            </li>
            <li>
              <b>{c.breaking}</b> breaking (users see it)
            </li>
            {c.wordingOnly ? (
              <li>
                <b>{c.wordingOnly}</b> wording only
              </li>
            ) : null}
          </ul>
          <p className="faint small">
            Computed {formatClock(n.computedAt)}, against{' '}
            {n.from ? shortBuild(n.from) : 'no earlier build'}.
          </p>
        </Card>
        <Card className="pad" role="region" aria-label="Package and quality">
          <h2 className="h2-sm">Package and quality</h2>
          {n.package ? (
            <>
              <Kv
                label="stream"
                value={`${n.package.from?.streamVersion ?? '?'} → ${n.package.to?.streamVersion ?? '?'}`}
                mono
              />
              <Kv
                label="rules"
                value={`${n.package.from?.rulesHash ?? '?'} → ${n.package.to?.rulesHash ?? '?'}`}
                mono
              />
            </>
          ) : null}
          {n.gold?.before && n.gold.after
            ? Object.keys(n.gold.after).map((k) => (
                <Kv
                  key={k}
                  label={k}
                  value={`${n.gold?.before?.[k] ?? '?'} → ${n.gold?.after?.[k] ?? '?'}`}
                  mono
                />
              ))
            : null}
          {!n.package && !n.gold ? (
            <p className="muted small">No package or quality data for this build.</p>
          ) : null}
        </Card>
      </div>

      <Card className="pad" role="region" aria-label="Review">
        <h2 className="h2-sm">Your review</h2>
        {canKeep || canRollForward ? (
          <div className="stack">
            <label htmlFor="keep-note" className="small">
              {canRollForward ? 'Note (optional)' : 'Note for the record (optional)'}
            </label>
            <input
              id="keep-note"
              className="input"
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        ) : null}
        <div className="row" style={{ marginTop: 12 }}>
          {canKeep ? (
            <Button variant="primary" disabled={busy !== null} onClick={() => void keep()}>
              {busy === 'keep' ? 'Keeping…' : 'Keep this build'}
            </Button>
          ) : null}
          {canRollForward ? (
            <Button variant="primary" disabled={busy !== null} onClick={() => void keep()}>
              {busy === 'keep' ? 'Rolling forward…' : 'Roll forward'}
            </Button>
          ) : null}
          {canRollBack && !confirm ? (
            <Button disabled={busy !== null} onClick={() => setConfirm(true)}>
              Roll back…
            </Button>
          ) : null}
          <Button disabled={busy !== null} onClick={() => void copyIssues()}>
            {busy === 'copy' ? 'Building…' : 'Copy issues'}
          </Button>
          <Button disabled={busy !== null} onClick={() => void downloadIssues()}>
            {busy === 'download' ? 'Building…' : 'Download issues (.md)'}
          </Button>
          <span role="status" className="faint small">
            {copied === 'ok'
              ? 'Issues copied: paste them to stream'
              : copied === 'fail'
                ? 'Copy failed: use the download instead'
                : ''}
          </span>
        </div>
        {canRollForward ? (
          <p className="small muted">
            This build was rolled back. Rolling forward makes it `latest` again, as long as `latest`
            is still its previous build.
          </p>
        ) : null}
        {decided && !canRollForward ? (
          <p className="small muted">This build is {REVIEW_LABEL[n.review].toLowerCase()}.</p>
        ) : null}
        {!n.from ? (
          <p className="small muted">This is the first build: there is nothing to roll back to.</p>
        ) : null}
        {!n.tagged && n.review !== 'rolled_back' && n.from ? (
          <p className="small muted">This build is not `latest`, so it cannot be rolled back.</p>
        ) : null}
        {confirm ? (
          <div className="rollback-confirm" role="group" aria-label="Roll back this build">
            <p>
              <b>Roll back {shortBuild(buildId)}?</b> The tag <span className="mono">latest</span>{' '}
              moves back to{' '}
              <span className="mono">{n.from ? shortBuild(n.from) : 'the previous build'}</span>.
              This build stays loaded and untagged, and you can roll it forward again while that
              build is still <span className="mono">latest</span>.
            </p>
            <label htmlFor="rollback-reason" className="small">
              Reason (required, kept in the history)
            </label>
            <textarea
              id="rollback-reason"
              className="input"
              rows={3}
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <p className="faint small">{reason.length} of 500</p>
            <div className="row">
              <Button
                variant="primary"
                disabled={busy !== null || reason.trim() === ''}
                onClick={() => void rollBack()}
              >
                {busy === 'rollback' ? 'Rolling back…' : 'Roll back'}
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => setConfirm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
        {error ? (
          <p role="alert" className="form-error">
            {error}
          </p>
        ) : null}
      </Card>

      <section aria-label="Extraction report" className="release-report">
        <h2 className="h2-sm">Extraction report</h2>
        {n.report.length === 0 ? (
          <p className="muted">Nothing suspect: every change has source evidence.</p>
        ) : (
          <p className="muted small">
            These changes are NOT shown to users: the source page did not change, or there is no
            evidence either way. They are most likely the extractor&apos;s doing.
          </p>
        )}
        {n.report.map((g) => (
          <Card key={g.rule} className="pad" role="region" aria-label={g.title}>
            <h3 className="h3-sm">
              {g.title} <span className="faint small mono">{g.rule}</span>{' '}
              <Chip>{g.items.length}</Chip>
            </h3>
            <p className="muted small">{g.explanation}</p>
            <ul className="plain change-list">
              {g.items.map((i) => (
                <ChangeRow key={i.id} api={apiId} build={buildId} item={i} onChanged={retry} />
              ))}
            </ul>
          </Card>
        ))}
      </section>

      <section aria-label="Changes users see" className="release-visible">
        <h2 className="h2-sm">What users see</h2>
        {items.length === 0 ? (
          <p className="muted">
            No confirmed or likely changes: users see nothing new for this build.
          </p>
        ) : (
          <>
            <ul className="plain change-list">
              {items.slice(0, more ? items.length : SHOWN).map((i) => (
                <ChangeRow key={i.id} api={apiId} build={buildId} item={i} onChanged={retry} />
              ))}
            </ul>
            {items.length > SHOWN && !more ? (
              <Button onClick={() => setMore(true)}>Show all {items.length}</Button>
            ) : null}
          </>
        )}
      </section>

      <Card className="pad" role="region" aria-label="History">
        <h2 className="h2-sm">History</h2>
        {n.decisions.length === 0 ? (
          <p className="muted small">No decision yet.</p>
        ) : (
          <ol className="plain decisions">
            {[...n.decisions].reverse().map((d, i) => (
              <li key={`${d.at}-${i}`}>
                <b>{DECISION_LABEL[d.decision] ?? d.decision}</b> by {d.by}{' '}
                <span className="faint small">{formatDate(d.at)}</span>
                {d.reason || d.note ? <div className="small">{d.reason ?? d.note}</div> : null}
                {d.item ? <div className="mono small faint">{d.item}</div> : null}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </>
  );
}
