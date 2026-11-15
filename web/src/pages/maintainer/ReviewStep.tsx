import { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import type { DiffItem } from '@/api/types';
import {
  Banner,
  Button,
  Card,
  Chip,
  ErrorState,
  Kv,
  LoadingState,
  MethodBadge,
  Tile,
} from '@/components';
import { WizardFrame } from './WizardFrame';
import { stepFor, stepPath, useJob } from './useJob';

const TONE = { new: 'ok', changed: 'warn', removed: 'bad' } as const;
const LABEL = { new: 'New', changed: 'Changed', removed: 'Removed' } as const;

function Item({ i }: { i: DiffItem }) {
  return (
    <tr>
      <td>
        <Chip tone={TONE[i.change]}>{LABEL[i.change]}</Chip>
      </td>
      <td>
        {i.path && i.method ? (
          <div className="mono diff-path">
            <MethodBadge method={i.method} /> {i.path}
          </div>
        ) : (
          <b>{i.title}</b>
        )}
        <div className="muted small">{i.note}</div>
      </td>
      <td>
        <Chip>{i.kind}</Chip>
      </td>
    </tr>
  );
}

export function ReviewStep() {
  const { jobId = '' } = useParams();
  const client = useApiClient();
  const navigate = useNavigate();
  const { state, job, retry } = useJob(jobId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.status === 'error')
    return (
      <ErrorState title="Could not load this build" message={state.error.message} onRetry={retry} />
    );
  if (!job) return <LoadingState label="Loading the review" />;
  if (stepFor(job.status) !== 'review')
    return <Navigate to={stepPath(job, stepFor(job.status))} replace />;
  const { diff, plan } = job;
  if (!diff || !plan)
    return (
      <ErrorState
        title="Nothing to review"
        message="This build has no diff yet. Upload the package again."
      />
    );

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await client.startBuild(jobId);
      navigate(`/maintainer/jobs/${jobId}/build`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the build.');
      setBusy(false);
    }
  }

  return (
    <WizardFrame name={job.displayName} step={2}>
      <div className="diff">
        <Tile value={diff.counts.new} label="New" tone="n" />
        <Tile value={diff.counts.changed} label="Changed" tone="c" />
        <Tile value={diff.counts.removed} label="Removed" tone="r" />
        <Tile value={diff.counts.unchanged} label="Unchanged, kept as is" tone="u" />
      </div>
      <div className="two review">
        <Card className="pad">
          <div className="rowhead">
            <h2>What changed{diff.since ? ` since ${diff.since}` : ''}</h2>
            <span className="muted small">
              Showing {diff.items.length} of {diff.totalItems}
            </span>
          </div>
          {diff.items.length === 0 ? (
            <p className="muted">No changes: every chunk is identical to the live build.</p>
          ) : (
            <table>
              <caption className="sr-only">Changed items</caption>
              <thead>
                <tr>
                  <th scope="col">Change</th>
                  <th scope="col">Item</th>
                  <th scope="col">Kind</th>
                </tr>
              </thead>
              <tbody>
                {diff.items.map((i, n) => (
                  <Item key={`${i.change}-${i.title}-${n}`} i={i} />
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <div className="stack">
          <Card className="pad">
            <h2 className="h2-sm">Embedding plan</h2>
            <Kv
              label="Chunks to embed"
              value={
                <>
                  <b>{plan.toEmbed}</b> of {plan.total}
                </>
              }
            />
            <Kv label="Model" value={plan.model} />
            <Kv label="Dimensions" value={plan.dimensions} />
            <Kv label="Estimated tokens" value={plan.estimatedTokens} />
            <Kv label="Estimated cost" value={plan.estimatedCost} />
          </Card>
          <Banner tone="accent" title="Nothing goes live yet">
            {job.liveBuild
              ? `The build is staged in Postgres. Live search keeps using ${job.liveBuild} until you publish.`
              : 'The build is staged in Postgres. This API has no live build yet; nothing is searchable until you publish.'}
          </Banner>
        </div>
      </div>
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
      <div className="actions">
        <button
          type="button"
          className="linkbtn muted-link"
          onClick={() => navigate(`/maintainer/apis/${job.apiId}/update`)}
        >
          ← Back
        </button>
        <Button variant="primary" size="lg" onClick={() => void start()} disabled={busy}>
          Start build
        </Button>
      </div>
    </WizardFrame>
  );
}
