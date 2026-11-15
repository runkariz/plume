import { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { Banner, Button, Card, Chip, ErrorState, Kv, LoadingState } from '@/components';
import { WizardFrame } from './WizardFrame';
import { stepFor, stepPath, useJob } from './useJob';

export function PublishStep() {
  const { jobId = '' } = useParams();
  const client = useApiClient();
  const { state, job, setJob, retry } = useJob(jobId);
  const [busy, setBusy] = useState<'publish' | 'discard' | 'dump' | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.status === 'error')
    return (
      <ErrorState title="Could not load this build" message={state.error.message} onRetry={retry} />
    );
  if (!job) return <LoadingState label="Loading the quality gate" />;
  if (stepFor(job.status) !== 'publish')
    return <Navigate to={stepPath(job, stepFor(job.status))} replace />;

  async function run(kind: 'publish' | 'discard') {
    setBusy(kind);
    setError(null);
    try {
      setJob(kind === 'publish' ? await client.publishJob(jobId) : await client.discardJob(jobId));
      setConfirmDiscard(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not ${kind} the build.`);
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    setBusy('dump');
    setError(null);
    try {
      const blob = await client.downloadDump(jobId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = job?.eval?.release.knowledgeFile ?? `${job?.apiId ?? 'plume'}.dump.gz`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not download the dump.');
    } finally {
      setBusy(null);
    }
  }

  if (job.status === 'discarded')
    return (
      <WizardFrame name={job.displayName} step={4}>
        <Banner tone="warn" title="Build discarded">
          The staged build {job.stagedBuild} was removed. Live search is unchanged.
        </Banner>
        <div className="actions">
          <span />
          <Link className="btn primary" to="/maintainer">
            Back to maintainer
          </Link>
        </div>
      </WizardFrame>
    );

  const ev = job.eval;
  if (!ev)
    return <ErrorState title="No evaluation yet" message="This build has not been evaluated." />;
  const published = job.status === 'published';

  return (
    <WizardFrame name={job.displayName} step={4} allDone={published}>
      {published ? (
        <Banner tone="ok" icon title={`Published ${ev.release.version}`}>
          Live search now uses build {ev.release.version}.
        </Banner>
      ) : ev.gate.passed ? (
        <Banner tone="ok" icon title="Quality gate passed">
          {ev.gate.message}
        </Banner>
      ) : (
        <Banner tone="bad" title="Quality gate failed">
          {ev.gate.message}
        </Banner>
      )}
      <div className="two publish">
        <Card className="pad">
          <h2 className="h2-sm">Evaluation, staged vs live</h2>
          <table>
            <caption className="sr-only">
              Evaluation metrics, staged build against the live build
            </caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Live</th>
                <th scope="col">Staged</th>
                <th scope="col">
                  <span className="sr-only">Change</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {ev.metrics.map((m) => (
                <tr key={m.key}>
                  <td>{m.label}</td>
                  <td className="mono">{m.live}</td>
                  <td className="mono">
                    <b>{m.staged}</b>
                  </td>
                  <td>
                    <Chip tone={m.tone === 'neutral' ? 'neutral' : m.tone}>{m.delta}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="stack">
          <Card className="pad">
            <h2 className="h2-sm">Release</h2>
            <Kv label="Version" value={ev.release.version} mono />
            <Kv label="Knowledge file" value={ev.release.knowledgeFile} mono />
            <Kv label="Notes" value={ev.release.notes} />
          </Card>
          <Card className="pad">
            <h2 className="h2-sm">Publishing will</h2>
            <ul className="bullets muted">
              <li>Switch live search to the staged build</li>
              <li>Export the dump and attach it to a GitHub release</li>
              <li>Update the knowledge manifest</li>
            </ul>
          </Card>
        </div>
      </div>
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
      {published ? (
        <div className="actions">
          <span />
          <Link className="btn primary lg" to={`/apis/${job.apiId}`}>
            View {job.displayName}
          </Link>
        </div>
      ) : (
        <div className="actions">
          {confirmDiscard ? (
            <span className="row">
              <span>Discard the staged build?</span>
              <Button disabled={busy !== null} onClick={() => void run('discard')}>
                Yes, discard
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDiscard(false)}>
                Keep it
              </Button>
            </span>
          ) : (
            <button
              type="button"
              className="linkbtn muted-link"
              onClick={() => setConfirmDiscard(true)}
            >
              Discard build
            </button>
          )}
          <span className="row">
            <Button disabled={busy !== null} onClick={() => void download()}>
              Download dump
            </Button>
            <Button
              variant="primary"
              size="lg"
              disabled={!ev.gate.passed || busy !== null}
              onClick={() => void run('publish')}
            >
              Publish {ev.release.version}
            </Button>
          </span>
        </div>
      )}
    </WizardFrame>
  );
}
