import { useEffect, useRef, useState } from 'react';
import { useApiClient } from '@/api/context';
import type { Concept, DraftIssue, ModelJobEvent } from '@/api/types';
import { Banner, Button, Card, Chip } from '@/components';

interface Round {
  n: number;
  issues: DraftIssue[] | null; // null = still running or accepted
}

interface Progress {
  documents: number | null;
  fields: number | null;
  rounds: Round[];
  maxRounds: number;
  snapshotId: string | null;
  failure: string | null;
  finished: boolean;
}

const EMPTY: Progress = {
  documents: null,
  fields: null,
  rounds: [],
  maxRounds: 3,
  snapshotId: null,
  failure: null,
  finished: false,
};

export function reduce(p: Progress, e: ModelJobEvent): Progress {
  switch (e.type) {
    case 'context':
      return { ...p, documents: e.documents, fields: e.fields };
    case 'round':
      return {
        ...p,
        maxRounds: e.of,
        rounds: p.rounds.some((r) => r.n === e.n)
          ? p.rounds
          : [...p.rounds, { n: e.n, issues: null }],
      };
    case 'refused':
      return {
        ...p,
        rounds: p.rounds.map((r) => (r.n === e.round ? { ...r, issues: e.issues } : r)),
      };
    case 'accepted':
      return { ...p, snapshotId: e.snapshotId };
    case 'failed':
      return { ...p, failure: e.message };
    case 'done':
      return { ...p, finished: true, snapshotId: e.snapshotId ?? p.snapshotId };
    default:
      return p;
  }
}

/**
 * A signed-in maintainer's "Generate": Plume writes the model on the server and streams what it does. The result
 * is UNRELEASED: the page opens it for review (Release or Discard). A refused round shows why, the next round
 * starts by itself, and after the last round the job fails with the server's message.
 */
export function ModelJobProgress({
  concept,
  jobId,
  onOpen,
  onCancel,
  onUseClaude,
}: {
  concept: Concept;
  jobId: string;
  onOpen: (snapshotId: string) => void;
  onCancel: () => void;
  onUseClaude: () => void;
}) {
  const client = useApiClient();
  const [p, setP] = useState<Progress>(EMPTY);
  const [lost, setLost] = useState<string | null>(null);
  const focus = useRef<HTMLDivElement>(null);
  useEffect(() => focus.current?.focus(), []);

  useEffect(() => {
    const ctrl = new AbortController();
    client
      .watchModelJob(jobId, (e) => setP((prev) => reduce(prev, e)), ctrl.signal)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted)
          setLost(e instanceof Error ? e.message : 'The connection to the generation was lost.');
      });
    return () => ctrl.abort();
  }, [client, jobId]);

  // a finished, successful job opens the (unreleased) model for review
  useEffect(() => {
    if (p.finished && p.snapshotId && !p.failure) onOpen(p.snapshotId);
  }, [p.finished, p.snapshotId, p.failure, onOpen]);

  const failed = p.failure !== null || lost !== null;
  return (
    <Card className="pad session" role="region" aria-label="Generation on the server">
      <div ref={focus} tabIndex={-1} className="session-focus">
        <div className="rowhead">
          <h2>Generating {concept.name}</h2>
          {!failed && !p.finished ? (
            <span className="live">
              <span className="dot" aria-hidden /> Working on the server
            </span>
          ) : null}
        </div>
        <p className="muted">
          Plume reads the pinned docs, writes the model and checks every citation before it stores
          anything. The result is <b>unreleased</b>: you review it, then release or discard it.
        </p>
        <ol className="job-steps" aria-live="polite" aria-label="Progress">
          <li className={p.documents !== null ? 'done' : 'active'}>
            {p.documents !== null
              ? `Read ${p.documents} documents (${p.fields ?? 0} fields)`
              : 'Reading the docs…'}
          </li>
          {p.rounds.map((r) => (
            <li
              key={r.n}
              className={r.issues ? 'refused' : p.snapshotId || p.failure ? 'done' : 'active'}
            >
              Round {r.n} of {p.maxRounds}
              {r.issues ? (
                <>
                  :{' '}
                  <Chip tone="warn">
                    refused, {r.issues.length} issue{r.issues.length === 1 ? '' : 's'}
                  </Chip>
                  <ul className="draft-issues">
                    {r.issues.map((i, n) => (
                      <li key={`${i.code}-${i.field}-${n}`}>
                        <Chip tone="bad">{i.code}</Chip>{' '}
                        <span className="mono small">
                          {i.field}
                          {i.api ? ` / ${i.api}` : ''}
                        </span>
                        <div className="muted small">{i.message}</div>
                      </li>
                    ))}
                  </ul>
                </>
              ) : p.snapshotId ? (
                <>
                  : <Chip tone="ok">accepted</Chip>
                </>
              ) : null}
            </li>
          ))}
        </ol>
        {p.finished && p.snapshotId && !failed ? (
          <p role="status" className="muted">
            Done: opening the model for review…
          </p>
        ) : null}
        {failed ? (
          <Banner tone="bad" title="The model was not generated">
            {p.failure ?? lost} Nothing was stored.
            <div className="row" style={{ marginTop: 10 }}>
              <Button onClick={onUseClaude}>Use Claude instead</Button>
              <Button variant="ghost" onClick={onCancel}>
                Close
              </Button>
            </div>
          </Banner>
        ) : (
          <div className="actions session-actions">
            <button type="button" className="linkbtn muted-link" onClick={onCancel}>
              Stop watching
            </button>
            <span />
          </div>
        )}
      </div>
    </Card>
  );
}
