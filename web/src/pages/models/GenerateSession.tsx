import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import {
  ApiError,
  type ApiRef,
  type Concept,
  type DraftIssue,
  type GenerateResponse,
} from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Banner, Button, Card, Chip } from '@/components';
import { shortBuild } from '@/lib/format';
import { EvidencePack } from './EvidencePack';

/** How often the open session checks for the new model (tests lower it). */
export const pollConfig = { ms: 3000 };

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

function Issues({ issues }: { issues: DraftIssue[] }) {
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
 * Shown after "Generate" when the server needs a draft. Plume runs no LLM: Claude reads the evidence pack and
 * submits a draft through the maintainer MCP, or a signed-in maintainer pastes one. The page notices a new
 * snapshot by polling the model list and opens it.
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
  onOpen: (snapshotId: string) => void;
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

  // Poll for the snapshot Claude (or a maintainer) will create for this concept on these APIs.
  const apiIds = apis.map((a) => a.id);
  const key = apiIds.join(',');
  const firstApi = apiIds[0];
  useEffect(() => {
    if (!firstApi) return;
    const ids = key.split(',');
    const ctrl = new AbortController();
    const timer = setInterval(() => {
      client.listModels(firstApi, ctrl.signal).then(
        (r) => {
          const hit = r.items.find((m) => m.concept === concept.id && sameSet(m.apis, ids));
          if (hit && !ctrl.signal.aborted) onOpen(hit.id);
        },
        () => undefined, // a missed poll is not an error: try again on the next tick
      );
    }, pollConfig.ms);
    return () => {
      clearInterval(timer);
      ctrl.abort();
    };
  }, [client, firstApi, key, concept.id, onOpen]);

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
  const connectLine = session.maintainerMcpUrl
    ? `claude mcp add --transport http plume-maintainer ${session.maintainerMcpUrl} --header "Authorization: Bearer <your maintainer token>"`
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
    try {
      const { model } = await client.submitModelDraft(session.sessionId, parsed);
      onOpen(model.id);
    } catch (err) {
      if (err instanceof ApiError && err.issues?.length) setIssues(err.issues);
      else if (err instanceof ApiError && err.status === 401)
        setError('Your session is not valid any more. Sign in again.');
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
          Plume does not write models itself. Claude reads the evidence below, writes the canonical
          model, and Plume checks every citation before it stores anything. This page opens the
          model as soon as it exists.
        </p>
        <ol className="session-steps">
          <li>
            <b>Add the Plume maintainer connector to Claude</b> (once). It needs a maintainer token.
            {connectLine ? (
              <>
                <pre className="code prompt" aria-label="Command to add the maintainer connector">
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
          {maintainer ? (
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
              </div>
            </form>
          ) : (
            <Banner tone="accent" title="Maintainers can paste a draft">
              <Link to="/maintainer">Sign in as a maintainer</Link> to submit a draft here. The
              evidence pack format is in the pack above.
            </Banner>
          )}
          {!maintainer && error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
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
