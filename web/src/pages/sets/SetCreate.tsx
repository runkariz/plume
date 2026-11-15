import { useEffect, useReducer, useRef, useState } from 'react';
import { useApiClient } from '@/api/context';
import type { DraftIssue, ModelJobEvent, SetSessionResponse } from '@/api/types';
import { Banner, Button, Card, Chip } from '@/components';

/** How often the open session checks for the new set (tests lower it). */
export const setPollConfig = { ms: 3000 };

/**
 * "Create with Claude": the set session pins the builds once, Claude reads it through the connector, writes or
 * reuses a model per member, asks the person how each relation should be designed and submits the set. The page
 * only shows the prompt and watches the session; it opens the set when one is stored. Without a maintainer token
 * the set is stored unlisted (its link is its id), with one it is stored unreleased.
 */
export function SetSessionPanel({
  session,
  concepts,
  onOpen,
  onCancel,
}: {
  session: SetSessionResponse;
  concepts: string[];
  onOpen: (setId: string) => void;
  onCancel: () => void;
}) {
  const client = useApiClient();
  const focus = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');
  useEffect(() => focus.current?.focus(), []);

  const id = session.setSessionId;
  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setInterval(() => {
      client.getSetSession(id, ctrl.signal).then(
        (r) => {
          if (r.setId && !ctrl.signal.aborted) onOpen(r.setId);
        },
        () => undefined, // a missed poll is not an error: try again on the next tick
      );
    }, setPollConfig.ms);
    return () => {
      clearInterval(timer);
      ctrl.abort();
    };
  }, [client, id, onOpen]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(session.claudePrompt);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
    setTimeout(() => setCopied('idle'), 2500);
  }

  return (
    <Card className="pad session" role="region" aria-label="Create the set with Claude">
      <div ref={focus} tabIndex={-1} className="session-focus">
        <div className="rowhead">
          <h2>Create the set with Claude</h2>
          <span className="live">
            <span className="dot" aria-hidden /> Waiting for Claude
          </span>
        </div>
        <p className="muted">
          The builds of the APIs are pinned for this set: <b>{concepts.join(', ')}</b>. Claude
          writes a model for each (or reuses the ones that exist), asks you how each relation should
          be designed, and stores the set. This page opens it when it arrives.
        </p>
        <ol className="session-steps">
          <li>Use Claude with the Plume connector (the one used for single models).</li>
          <li>Paste this prompt:</li>
        </ol>
        <pre className="code prompt" aria-label="Prompt for Claude">
          {session.claudePrompt}
        </pre>
        <div className="row">
          <Button variant="primary" onClick={() => void copy()}>
            Copy prompt
          </Button>
          <a
            className="btn"
            href="https://claude.ai/new"
            target="_blank"
            rel="noreferrer"
            onClick={() => void copy()}
          >
            Open Claude
          </a>
          <span role="status" className="faint small">
            {copied === 'ok'
              ? 'Prompt copied: paste it into Claude'
              : copied === 'fail'
                ? 'Copy failed: select the text instead'
                : ''}
          </span>
        </div>
        <div className="actions session-actions">
          <button type="button" className="linkbtn muted-link" onClick={onCancel}>
            Cancel
          </button>
          <span />
        </div>
      </div>
    </Card>
  );
}

interface SetProgress {
  written: string[];
  proposals: { relations: string[]; openQuestions: number } | null;
  dropped: DraftIssue[];
  setId: string | null;
  failure: string | null;
  finished: boolean;
}

const EMPTY: SetProgress = {
  written: [],
  proposals: null,
  dropped: [],
  setId: null,
  failure: null,
  finished: false,
};

export function reduceSetJob(p: SetProgress, e: ModelJobEvent): SetProgress {
  switch (e.type) {
    case 'member':
      return p.written.includes(e.concept) ? p : { ...p, written: [...p.written, e.concept] };
    case 'proposals':
      return { ...p, proposals: { relations: e.relations, openQuestions: e.openQuestions } };
    case 'refused':
      return { ...p, dropped: e.issues };
    case 'accepted':
      return { ...p, setId: e.setId ?? p.setId };
    case 'failed':
      return { ...p, failure: e.message };
    case 'done':
      return { ...p, finished: true, setId: e.setId ?? p.setId };
    default:
      return p;
  }
}

/**
 * A signed-in maintainer's "Generate the set": Plume writes every member model on the server, then proposes the
 * relations from the documented candidates. They are UNDECIDED: the set opens for review, and the maintainer decides
 * each relation before releasing it. A failed member stops the job and nothing is stored.
 */
export function SetJobProgress({
  jobId,
  concepts,
  onOpen,
  onCancel,
  onUseClaude,
}: {
  jobId: string;
  concepts: string[];
  onOpen: (setId: string) => void;
  onCancel: () => void;
  onUseClaude: () => void;
}) {
  const client = useApiClient();
  const [p, dispatch] = useReducer(reduceSetJob, EMPTY);
  const [lost, setLost] = useState<string | null>(null);
  const focus = useRef<HTMLDivElement>(null);
  useEffect(() => focus.current?.focus(), []);

  useEffect(() => {
    const ctrl = new AbortController();
    client
      .watchModelJob(jobId, (e) => dispatch(e), ctrl.signal)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted)
          setLost(e instanceof Error ? e.message : 'The connection to the generation was lost.');
      });
    return () => ctrl.abort();
  }, [client, jobId]);

  useEffect(() => {
    if (p.finished && p.setId && !p.failure) onOpen(p.setId);
  }, [p.finished, p.setId, p.failure, onOpen]);

  const failed = p.failure !== null || lost !== null;
  const nextUp = failed ? null : concepts.find((c) => !p.written.includes(c));
  return (
    <Card className="pad session" role="region" aria-label="Generation of the set on the server">
      <div ref={focus} tabIndex={-1} className="session-focus">
        <div className="rowhead">
          <h2>Generating the set</h2>
          {!failed && !p.finished ? (
            <span className="live">
              <span className="dot" aria-hidden /> Working on the server
            </span>
          ) : null}
        </div>
        <p className="muted">
          Plume writes a model for each concept, checking every citation, then proposes the
          relations the docs support. Every relation is <b>undecided</b> until you decide it; the
          set is <b>unreleased</b>.
        </p>
        <ol className="job-steps" aria-live="polite" aria-label="Progress">
          {concepts.map((c) => (
            <li
              key={c}
              className={p.written.includes(c) ? 'done' : c === nextUp ? 'active' : undefined}
            >
              {p.written.includes(c) ? (
                <>
                  {c}: <Chip tone="ok">model written</Chip>
                </>
              ) : c === nextUp ? (
                `Writing the ${c} model…`
              ) : (
                `${c}: waiting`
              )}
            </li>
          ))}
          <li
            className={
              p.proposals ? 'done' : p.written.length === concepts.length ? 'active' : undefined
            }
          >
            {p.proposals
              ? `Proposed ${p.proposals.relations.length} ${p.proposals.relations.length === 1 ? 'relation' : 'relations'} to decide${
                  p.proposals.openQuestions
                    ? `, ${p.proposals.openQuestions} open ${p.proposals.openQuestions === 1 ? 'question' : 'questions'}`
                    : ''
                }`
              : 'Proposing the relations'}
          </li>
        </ol>
        {p.dropped.length ? (
          <Banner tone="warn" title="Some proposed relations were not valid">
            They were left out; decide them yourself in the set.
            <ul className="draft-issues">
              {p.dropped.map((i, n) => (
                <li key={`${i.code}-${i.field}-${n}`}>
                  <Chip tone="bad">{i.code}</Chip> <span className="mono small">{i.field}</span>
                  <div className="muted small">{i.message}</div>
                </li>
              ))}
            </ul>
          </Banner>
        ) : null}
        {p.finished && p.setId && !failed ? (
          <p role="status" className="muted">
            Done: opening the set for review…
          </p>
        ) : null}
        {failed ? (
          <Banner tone="bad" title="The set was not generated">
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
