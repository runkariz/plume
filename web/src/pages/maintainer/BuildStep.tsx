import { useEffect, useReducer, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { STEP_KEYS, type StepStatus } from '@/api/types';
import { Banner, Button, Card, ErrorState, LoadingState } from '@/components';
import { CheckIcon } from '@/icons';
import { buildReducer, initialBuildState, STEP_TITLES } from './buildState';
import { WizardFrame } from './WizardFrame';
import { stepFor, stepPath, useJob } from './useJob';

const SRC_LABEL = { plume: 'plume', postgres: 'postgres', gemini: 'gemini' } as const;
const VISIBLE_LOG_LINES = 12;

function StepIcon({ status }: { status: StepStatus }) {
  if (status === 'done')
    return (
      <span className="ck" aria-hidden>
        <CheckIcon />
      </span>
    );
  if (status === 'failed')
    return (
      <span className="ck bad" aria-hidden>
        !
      </span>
    );
  if (status === 'running') return <span className="ck run spin" aria-hidden />;
  return <span className="ck wait" aria-hidden />;
}

const STATUS_TEXT: Record<StepStatus, string> = {
  pending: 'waiting',
  running: 'running',
  done: 'done',
  failed: 'failed',
};

export function BuildStep() {
  const { jobId = '' } = useParams();
  const client = useApiClient();
  const navigate = useNavigate();
  const { state: jobState, job, setJob, retry } = useJob(jobId);
  const [build, dispatch] = useReducer(buildReducer, undefined, initialBuildState);
  const [attempt, setAttempt] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);

  const watching = (job !== null && stepFor(job.status) === 'build') || job?.status === 'staged';

  useEffect(() => {
    if (!watching) return;
    const ctrl = new AbortController();
    dispatch({ type: 'reset' });
    client
      .watchJob(jobId, (e) => dispatch(e), ctrl.signal)
      .then(
        () => {
          if (!ctrl.signal.aborted) void client.getJob(jobId).then(setJob, () => undefined);
        },
        (e: unknown) => {
          if (!ctrl.signal.aborted)
            dispatch({
              type: 'lost',
              message: e instanceof Error ? e.message : 'Lost the connection to the build.',
            });
        },
      );
    return () => ctrl.abort();
    // `watching` flips once when the job first loads; setJob and client are stable.
  }, [client, jobId, watching, attempt, setJob]);

  if (jobState.status === 'error')
    return (
      <ErrorState
        title="Could not load this build"
        message={jobState.error.message}
        onRetry={retry}
      />
    );
  if (!job) return <LoadingState label="Loading the build" />;
  if (!watching) return <Navigate to={stepPath(job, stepFor(job.status))} replace />;

  async function retryBuild() {
    setActionError(null);
    try {
      setJob(await client.startBuild(jobId));
      setAttempt((n) => n + 1);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not restart the build.');
    }
  }

  async function discard() {
    setActionError(null);
    try {
      await client.discardJob(jobId);
      navigate(`/maintainer/jobs/${jobId}/publish`);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not discard the build.');
    }
  }

  const { progress } = build;
  const pct =
    progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const lines = build.logs.slice(-VISIBLE_LOG_LINES);
  const live = build.phase === 'live' || build.phase === 'connecting';

  return (
    <WizardFrame
      name={job.displayName}
      step={3}
      aside={
        live ? (
          <span className="live">
            <span className="dot" aria-hidden /> Live
          </span>
        ) : null
      }
    >
      <div className="build">
        <div className="stack">
          <Card className="pad">
            <div className="rowhead">
              <h2>Embedding changed chunks</h2>
              <span className="mono" aria-hidden>
                {progress ? `${progress.done} / ${progress.total}` : '– / –'}
              </span>
            </div>
            <div
              className="progress"
              role="progressbar"
              aria-label="Embedding progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              aria-valuetext={
                progress ? `${progress.done} of ${progress.total} chunks` : 'not started'
              }
            >
              <i style={{ width: `${pct}%` }} />
            </div>
            <p className="faint small">
              {build.phase === 'staged'
                ? 'Embedding finished.'
                : progress?.etaSeconds
                  ? `About ${progress.etaSeconds} s left`
                  : 'Waiting for the first batch'}
            </p>
          </Card>
          <Card className="pad">
            <h2 className="h2-sm">Pipeline</h2>
            <ol className="pipeline">
              {STEP_KEYS.map((k) => {
                const s = build.steps[k];
                return (
                  <li key={k} className="check">
                    <StepIcon status={s.status} />
                    <div>
                      <div className="t">
                        {STEP_TITLES[k]} <span className="sr-only">({STATUS_TEXT[s.status]})</span>
                      </div>
                      <div className="d">{s.detail}</div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </Card>
        </div>
        <div className="stack">
          <div className="svc-row">
            <Card className="conn">
              <span className="ic pg" aria-hidden>
                PG
              </span>
              <div>
                <b>Postgres</b>
                <div className="muted small">{build.services.postgres ?? 'Connecting…'}</div>
              </div>
            </Card>
            <Card className="conn">
              <span className="ic gm" aria-hidden>
                G
              </span>
              <div>
                <b>Gemini</b>
                <div className="muted small">{build.services.gemini ?? 'Waiting'}</div>
              </div>
            </Card>
          </div>
          <div className="log" aria-label="Live events">
            <h2 className="log-title">Live events</h2>
            <div role="log" aria-live="off" aria-label="Build events">
              {lines.length === 0 ? <div className="t">Waiting for the first event…</div> : null}
              {lines.map((l, i) => (
                <div key={l.id} className={i === lines.length - 1 && live ? 'now' : undefined}>
                  <span className="t">{l.t}</span>{' '}
                  <span className={`src ${l.source}`}>{SRC_LABEL[l.source]}</span> {l.message}
                </div>
              ))}
            </div>
          </div>
          {build.phase === 'lost' ? (
            <Banner tone="warn" title="Lost the connection to the build">
              {build.message ?? 'The event stream was interrupted.'} The build keeps running on the
              server.
            </Banner>
          ) : null}
          {build.phase === 'failed' ? (
            <Banner tone="bad" title="The build failed">
              {build.message ?? 'A step failed. Nothing was published.'}
            </Banner>
          ) : null}
        </div>
      </div>
      {actionError ? (
        <p role="alert" className="form-error">
          {actionError}
        </p>
      ) : null}
      <div className="actions">
        {build.phase === 'failed' ? (
          <>
            <button type="button" className="linkbtn muted-link" onClick={() => void discard()}>
              Discard build
            </button>
            <Button variant="primary" size="lg" onClick={() => void retryBuild()}>
              Retry build
            </Button>
          </>
        ) : build.phase === 'lost' ? (
          <>
            <Link to="/maintainer" className="muted-link">
              Leave
            </Link>
            <Button variant="primary" size="lg" onClick={() => setAttempt((n) => n + 1)}>
              Reconnect
            </Button>
          </>
        ) : (
          <>
            <span />
            <Button
              variant="primary"
              size="lg"
              disabled={build.phase !== 'staged' || job.status !== 'staged'}
              onClick={() => navigate(`/maintainer/jobs/${jobId}/publish`)}
            >
              Review quality gate →
            </Button>
          </>
        )}
      </div>
    </WizardFrame>
  );
}
