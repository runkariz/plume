import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useApiClient } from '@/api/context';
import {
  ApiError,
  type ApiRef,
  type Concept,
  type DraftIssue,
  type GenerateResponse,
  type CollectionRef,
} from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Button, Card, Chip } from '@/components';
import { readCollectionId, rememberCollection } from '@/lib/collection';
import { shortBuild } from '@/lib/format';
import { EvidencePack } from './EvidencePack';

/** How often the open session checks for the new model (tests lower it). */
export const pollConfig = { ms: 3000 };

export function Issues({ issues }: { issues: DraftIssue[] }) {
  return (
    <div role="alert" className="draft-issues">
      <b>The draft was refused, nothing was stored.</b>
      <ul>
        {issues.map((i, n) => (
          <li key={`${i.code}-${i.field}-${i.api ?? ''}-${n}`}>
            <Chip tone="bad">{i.code}</Chip>{' '}
            <span className="mono">
              {i.field}
              {i.api ? ` / ${i.api}` : ''}
            </span>
            <div className="muted small">{i.message}</div>
          </li>
        ))}
      </ul>
      <p className="small muted">Fix the listed mappings (or drop them) and submit again.</p>
    </div>
  );
}

/**
 * Shown after "Generate" with Claude: Claude reads the evidence pack and submits a draft through the connector,
 * or the person pastes a draft (anyone can). Without a maintainer token the model is stored unlisted (its link
 * is its id), with one it is stored unreleased. The page notices the new model by polling the session and opens it.
 */
export function GenerateSession({
  concept,
  apis,
  session,
  onOpen,
  onCancel,
}: {
  concept: Concept;
  apis: ApiRef[];
  session: GenerateResponse;
  onOpen: (snapshotId: string, extra?: { collection?: CollectionRef | null }) => void;
  onCancel: () => void;
}) {
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [copiedLine, setCopiedLine] = useState(false);
  const [showPack, setShowPack] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<DraftIssue[]>([]);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  // Poll the session: a draft accepted for it (by Claude or pasted elsewhere) names the model to open.
  // While a pasted draft is being submitted the poll must not open the model: the submit knows the My models link, the
  // poll does not, and whichever navigates last wins (the key and the "saved" notice would be lost).
  const submitting = useRef(false);
  const sessionId = session.sessionId;
  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setInterval(() => {
      client.getModelSession(sessionId, ctrl.signal).then(
        (r) => {
          if (r.snapshotId && !ctrl.signal.aborted && !submitting.current) onOpen(r.snapshotId);
        },
        () => undefined, // a missed poll is not an error: try again on the next tick
      );
    }, pollConfig.ms);
    return () => {
      clearInterval(timer);
      ctrl.abort();
    };
  }, [client, sessionId, onOpen]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(session.claudePrompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError('Copy failed: select the prompt and copy it by hand.');
    }
  }

  // A copy-ready connect line. The token is a placeholder: the web app never writes a real token into text.
  // Signed in: the maintainer connector (needs the token). Otherwise the reader connector, whatever the server
  // sent: it returns the maintainer URL to everyone.
  const maintainerConnector = maintainer && Boolean(session.maintainerMcpUrl);
  const connectLine = maintainerConnector
    ? `claude mcp add --transport http plume-maintainer ${session.maintainerMcpUrl} --header "Authorization: Bearer <your maintainer token>"`
    : session.mcpUrl
      ? `claude mcp add --transport http plume ${session.mcpUrl}`
      : null;

  async function copyLine() {
    if (!connectLine) return;
    try {
      await navigator.clipboard.writeText(connectLine);
      setCopiedLine(true);
      setTimeout(() => setCopiedLine(false), 2500);
    } catch {
      setError('Copy failed: select the command and copy it by hand.');
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIssues([]);
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch {
      setError('That is not valid JSON. Paste the whole draft object.');
      return;
    }
    setBusy(true);
    submitting.current = true;
    try {
      // someone without a token: the model joins the My models collection this browser holds, or starts one
      const sent = readCollectionId();
      const { model, collection } = await client.submitModelDraft(
        session.sessionId,
        parsed,
        undefined,
        { collection: sent },
      );
      rememberCollection(collection, sent);
      onOpen(model.id, collection ? { collection } : undefined);
    } catch (err) {
      submitting.current = false;
      if (err instanceof ApiError && err.issues?.length) setIssues(err.issues);
      else if (err instanceof ApiError && err.status === 401)
        setError('Your session is not valid any more. Sign in again.');
      else if (err instanceof ApiError && err.status === 413)
        setError('That draft is too large for the server.');
      else setError(err instanceof Error ? err.message : 'Could not submit the draft.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="pad session" role="region" aria-label="Generation session">
      <div ref={ref} tabIndex={-1} className="session-focus">
        <div className="rowhead">
          <h2>Waiting for a draft: {concept.name}</h2>
          <span className="live">
            <span className="dot" aria-hidden /> Checking for the new model
          </span>
        </div>
        <p className="muted">
          Claude reads the evidence below, writes the canonical model, and Plume checks every
          citation before it stores anything. This page opens the model as soon as it exists.{' '}
          {maintainer ? (
            <>
              Because you are signed in, the result is <b>unreleased</b> until you release it.
            </>
          ) : (
            <>
              The model is stored <b>unlisted</b>: only people with its link can open it, and it
              stays out of the public list.
            </>
          )}
        </p>
        <ol className="session-steps">
          <li>
            <b>Add the Plume connector to Claude</b> (once).
            {maintainerConnector ? ' It needs a maintainer token.' : null}
            {connectLine ? (
              <>
                <pre
                  className="code prompt"
                  aria-label={
                    maintainerConnector
                      ? 'Command to add the maintainer connector'
                      : 'Command to add the Plume connector'
                  }
                >
                  {connectLine}
                </pre>
                <div className="row">
                  <Button onClick={() => void copyLine()}>Copy command</Button>
                  <span role="status" className="faint small">
                    {copiedLine ? 'Command copied: put your token in place of the placeholder' : ''}
                  </span>
                </div>
              </>
            ) : null}
          </li>
          <li>
            <b>Give Claude this prompt.</b>
            <pre className="code prompt" aria-label="Prompt for Claude">
              {session.claudePrompt}
            </pre>
            <div className="row">
              <Button onClick={() => void copy()}>Copy prompt</Button>
              <a className="btn" href="https://claude.ai/new" target="_blank" rel="noreferrer">
                Open Claude
              </a>
              <span role="status" className="faint small">
                {copied ? 'Prompt copied: paste it into Claude' : ''}
              </span>
            </div>
          </li>
          <li>
            <b>Claude reads the evidence pack</b> for the builds pinned below.{' '}
            <button type="button" className="linkbtn small" onClick={() => setShowPack((v) => !v)}>
              {showPack ? 'Hide the evidence pack' : 'See what Plume gives Claude'}
            </button>
            {showPack ? <EvidencePack sessionId={session.sessionId} apis={apis} /> : null}
          </li>
          <li>
            <b>Claude submits the draft.</b> Plume refuses it with precise issue codes if a quote,
            field or endpoint is not in the pinned builds.
          </li>
        </ol>
        <ul className="pinned" aria-label="Pinned builds">
          {session.inputs.map((i) => {
            const api = apis.find((a) => a.id === i.api);
            return (
              <li key={i.api}>
                <Chip>{api?.shortName ?? i.api}</Chip>{' '}
                <span className="mono small" title={i.build}>
                  {shortBuild(i.build)}
                </span>
              </li>
            );
          })}
        </ul>
        <div className="session-draft">
          <h3>Or paste a draft yourself</h3>
          <form onSubmit={submit} noValidate>
            <label htmlFor="draft-json" className="sr-only">
              Draft JSON
            </label>
            <textarea
              id="draft-json"
              className="input mono draft-box"
              rows={7}
              spellCheck={false}
              placeholder='{ "name": "Order", "fields": [ … ] }'
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            {error ? (
              <p role="alert" className="form-error">
                {error}
              </p>
            ) : null}
            {issues.length ? <Issues issues={issues} /> : null}
            <div className="row" style={{ marginTop: 12 }}>
              <Button type="submit" variant="primary" disabled={busy || draft.trim() === ''}>
                {busy ? 'Checking the draft…' : 'Submit draft'}
              </Button>
              <span className="faint small">
                {maintainer ? 'Stored unreleased.' : 'Stored unlisted: only people with the link.'}
              </span>
            </div>
          </form>
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
