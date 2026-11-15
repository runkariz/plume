import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { ApiError, type ModelSnapshot, type ModelVisibility } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Banner, Button, Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { shareLink } from '@/lib/ownerKeys';

/** Official = released by a maintainer; unlisted = anyone with the link; unreleased = waiting for review. */
export function VisibilityChip({
  visibility,
  short = false,
}: {
  visibility?: ModelVisibility;
  short?: boolean;
}) {
  if (visibility === 'official') return <Chip tone="ok">Official</Chip>;
  if (visibility === 'unlisted')
    return <Chip tone="info">{short ? 'Unlisted' : 'Unlisted: anyone with the link'}</Chip>;
  if (visibility === 'unreleased') return <Chip tone="warn">Unreleased</Chip>;
  if (visibility === 'discarded') return <Chip tone="bad">Discarded</Chip>;
  return null;
}

/** "v3 of 3, based on <id>". A link to the model it was revised from; the other versions are in the history. */
export function LineageLine({
  snap,
  basePath = '/models',
}: {
  snap: Pick<ModelSnapshot, 'lineage'>;
  /** Where the other versions are shown: "/models" or "/model-sets". */
  basePath?: string;
}) {
  const l = snap.lineage;
  if (!l || (l.versions <= 1 && !l.basedOn)) return null;
  return (
    <p className="lineage muted small">
      <b>
        v{l.version} of {l.versions}
      </b>
      {l.basedOn ? (
        <>
          , based on <Link to={`${basePath}/${l.basedOn}`}>{l.basedOn}</Link>
        </>
      ) : null}
    </p>
  );
}

/** The other versions of this model; the page says when a newer one exists. */
export function LineageHistory({
  snap,
  basePath = '/models',
  what = 'model',
}: {
  snap: Pick<ModelSnapshot, 'id' | 'lineage'>;
  basePath?: string;
  what?: string;
}) {
  const l = snap.lineage;
  if (!l || l.history.length <= 1) return null;
  return (
    <>
      {l.latestId !== snap.id ? (
        <Banner tone="accent" title={`A newer version of this ${what} exists`}>
          This is version {l.version} of {l.versions}.{' '}
          <Link to={`${basePath}/${l.latestId}`}>Open the latest version</Link>.
        </Banner>
      ) : null}
      <details className="lineage-history">
        <summary>
          Versions of this {what} ({l.history.length})
        </summary>
        <ol>
          {l.history.map((h) => (
            <li key={h.id}>
              <span className="mono small">v{h.version}</span>{' '}
              {h.id === snap.id ? (
                <b>this version</b>
              ) : (
                <Link to={`${basePath}/${h.id}`} className="mono small">
                  {h.id}
                </Link>
              )}{' '}
              <span className="faint small">{formatDate(h.createdAt)}</span>{' '}
              <VisibilityChip visibility={h.visibility} short />
            </li>
          ))}
        </ol>
      </details>
    </>
  );
}

function useCopy() {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setState('ok');
    } catch {
      setState('fail');
    }
    setTimeout(() => setState('idle'), 2500);
  }
  return { state, copy };
}

/** An unlisted model: its link is its id, so the page says so and makes the link easy to copy. */
export function ShareCard({
  snap,
  what = 'model',
}: {
  snap: Pick<ModelSnapshot, 'id' | 'visibility' | 'sharePath'>;
  what?: string;
}) {
  const { state, copy } = useCopy();
  if (snap.visibility !== 'unlisted') return null;
  const link = shareLink(snap);
  return (
    <Card className="pad share-card" role="region" aria-label={`Share this ${what}`}>
      <h2 className="h2-sm">Share this {what}</h2>
      <p className="muted small">
        Anyone with this link can open the {what}. It is not in the public Models list.
      </p>
      <div className="share-row">
        <label htmlFor="share-link" className="sr-only">
          Link to this {what}
        </label>
        <input
          id="share-link"
          className="input mono"
          readOnly
          value={link}
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button onClick={() => void copy(link)}>Copy link</Button>
      </div>
      <span role="status" className="faint small">
        {state === 'ok'
          ? 'Link copied'
          : state === 'fail'
            ? 'Copy failed: select the link instead'
            : ''}
      </span>
    </Card>
  );
}

/** "Modify with Claude": the server builds the prompt (it names the tools), the web only copies it. */
export function ReviseCard({
  snap,
  what = 'model',
}: {
  snap: Pick<ModelSnapshot, 'visibility' | 'revisePrompt'>;
  what?: string;
}) {
  const { state, copy } = useCopy();
  if (!snap.revisePrompt) return null;
  const prompt = snap.revisePrompt;
  return (
    <Card className="pad revise-card" role="region" aria-label="Modify with Claude">
      <h2 className="h2-sm">Modify with Claude</h2>
      <p className="muted small">
        Ask Claude to change this {what}. Plume checks every citation again and stores the result as
        a new version{snap.visibility === 'official' ? ' of your own' : ''}; this {what} stays as it
        is.
      </p>
      <pre className="code prompt" aria-label="Prompt for Claude">
        {prompt}
      </pre>
      <div className="row">
        <Button onClick={() => void copy(prompt)}>Copy prompt</Button>
        <a
          className="btn"
          href="https://claude.ai/new"
          target="_blank"
          rel="noreferrer"
          onClick={() => void copy(prompt)}
        >
          Open Claude
        </a>
        <span role="status" className="faint small">
          {state === 'ok'
            ? 'Prompt copied: paste it into Claude'
            : state === 'fail'
              ? 'Copy failed: select the text instead'
              : ''}
        </span>
      </div>
    </Card>
  );
}

/** Shown right after someone without a token created a model: the owner key lists "Your models" in this browser. */
export function OwnerKeyNotice({
  ownerKey,
  onClose,
  what = 'model',
}: {
  ownerKey: string;
  onClose: () => void;
  what?: string;
}) {
  const { state, copy } = useCopy();
  return (
    <Banner tone="accent" title={`Your ${what} is saved, and unlisted`}>
      <p>
        Only people with this page's link can open it. This browser remembers the {what} under{' '}
        <b>Your {what}s</b> on the Models page. To see it from another browser, keep this key:
      </p>
      <div className="share-row">
        <code className="mono owner-key">{ownerKey}</code>
        <Button onClick={() => void copy(ownerKey)}>Copy key</Button>
        <Button variant="ghost" onClick={onClose}>
          Dismiss
        </Button>
      </div>
      <span role="status" className="faint small">
        {state === 'ok' ? 'Key copied' : ''}
      </span>
    </Banner>
  );
}

/** A maintainer reviews an unreleased model, then releases it (official, public) or discards it. */
export function ReviewBanner({ snap, onChanged }: { snap: ModelSnapshot; onChanged: () => void }) {
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const [busy, setBusy] = useState<'release' | 'discard' | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (snap.visibility !== 'unreleased') return null;

  async function run(action: 'release' | 'discard') {
    setBusy(action);
    setError(null);
    try {
      if (action === 'release') await client.releaseModel(snap.id);
      else await client.discardModel(snap.id);
      setConfirmDiscard(false);
      onChanged();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? 'Your session is not valid any more. Sign in again.'
          : e instanceof ApiError && e.status === 409
            ? 'This model is not waiting for review any more: someone else released or discarded it. Reload to see its state.'
            : e instanceof Error
              ? e.message
              : `Could not ${action} the model.`,
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <Banner tone="warn" title="Unreleased: waiting for your review">
      <p>
        {snap.generator
          ? `Written by ${snap.generator === 'claude' ? 'Claude' : snap.generator}. `
          : ''}
        Only signed-in maintainers can see it. Check the mappings and citations below, then release
        it to make it an <b>Official</b> model in the public list, or discard it.
      </p>
      {maintainer ? (
        <div className="row">
          <Button variant="primary" disabled={busy !== null} onClick={() => void run('release')}>
            {busy === 'release' ? 'Releasing…' : 'Release'}
          </Button>
          {confirmDiscard ? (
            <>
              <span className="small">Discard this model? It cannot be undone.</span>
              <Button disabled={busy !== null} onClick={() => void run('discard')}>
                {busy === 'discard' ? 'Discarding…' : 'Yes, discard'}
              </Button>
              <Button
                variant="ghost"
                disabled={busy !== null}
                onClick={() => setConfirmDiscard(false)}
              >
                Keep it
              </Button>
            </>
          ) : (
            <Button disabled={busy !== null} onClick={() => setConfirmDiscard(true)}>
              Discard
            </Button>
          )}
        </div>
      ) : (
        <p className="small">
          <Link to="/maintainer">Sign in as a maintainer</Link> to release or discard it.
        </p>
      )}
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
    </Banner>
  );
}
