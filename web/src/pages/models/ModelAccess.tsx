import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { ApiError, type ModelSnapshot, type ModelVisibility, type Supersedable } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Banner, Button, Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { shareLink } from '@/lib/ownerKeys';
import { ReleaseChoice } from './ReleaseChoice';
import { groupWarnings, WARNINGS_ID } from './warnings';

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
  if (visibility === 'superseded') return <Chip tone="warn">Superseded</Chip>;
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

/** A model a newer one replaced: still readable by its id, no longer in the lists. */
export function SupersededBanner({
  snap,
  basePath = '/models',
  what = 'model',
}: {
  snap: Pick<ModelSnapshot, 'supersededBy'>;
  basePath?: string;
  what?: string;
}) {
  if (!snap.supersededBy) return null;
  return (
    <Banner tone="accent" title={`Superseded by ${snap.supersededBy}`}>
      A newer {what} replaced this one:{' '}
      <Link to={`${basePath}/${snap.supersededBy}`}>open {snap.supersededBy}</Link>. This one stays
      readable by its link but is not in the lists any more.
    </Banner>
  );
}

/** "Replaces ...": the official models this one superseded when it was released. */
export function SupersedesLine({
  snap,
  basePath = '/models',
  what = 'models',
}: {
  snap: Pick<ModelSnapshot, 'supersedes'>;
  basePath?: string;
  what?: string;
}) {
  const ids = snap.supersedes ?? [];
  if (ids.length === 0) return null;
  return (
    <p className="supersedes muted small">
      Replaced these official {what} when it was released:{' '}
      {ids.map((id, i) => (
        <span key={id}>
          {i > 0 ? ', ' : ''}
          <Link to={`${basePath}/${id}`} className="mono">
            {id}
          </Link>
        </span>
      ))}
    </p>
  );
}

/** "Other versions of this concept": other official models of the same concept over the same APIs. */
export function SameConceptLine({ snap }: { snap: Pick<ModelSnapshot, 'id' | 'sameConcept'> }) {
  const others = (snap.sameConcept ?? []).filter((id) => id !== snap.id);
  if (others.length === 0) return null;
  return (
    <p className="same-concept muted small">
      Other official models of this concept over the same APIs:{' '}
      {others.map((id, i) => (
        <span key={id}>
          {i > 0 ? ', ' : ''}
          <Link to={`/models/${id}`} className="mono">
            {id}
          </Link>
        </span>
      ))}
    </p>
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

/**
 * On an official model's page, for a maintainer: retire older official models of the same concept after the fact
 * (the same choice as at release). Nothing is retired unless ticked; the answer reloads the page.
 */
export function RetirePanel({
  snap,
  onChanged,
}: {
  snap: ModelSnapshot;
  /** Called with the server's answer (it names what was replaced). */
  onChanged: (answer?: ModelSnapshot) => void;
}) {
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const [candidates, setCandidates] = useState<Supersedable[] | null>(null);
  const [none, setNone] = useState(false);
  const [busy, setBusy] = useState<'load' | 'retire' | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!maintainer || snap.visibility !== 'official') return null;

  async function open() {
    setBusy('load');
    setError(null);
    setNone(false);
    try {
      const found = await client.listSupersedable(snap.id);
      setNone(found.length === 0);
      setCandidates(found.length ? found : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not look for older models.');
    } finally {
      setBusy(null);
    }
  }

  async function retire(ids: string[]) {
    setBusy('retire');
    setError(null);
    try {
      const answer = await client.supersedeModels(snap.id, ids);
      setCandidates(null);
      onChanged(answer);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? `Nothing was retired: one of them is no longer an official model of this concept (${e.message}). Look again.`
          : e instanceof ApiError && e.status === 401
            ? 'Your session is not valid any more. Sign in again.'
            : e instanceof Error
              ? e.message
              : 'Could not retire them.',
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="pad retire-panel" role="region" aria-label="Retire older models">
      {candidates ? (
        <ReleaseChoice
          mode="retire"
          candidates={candidates}
          apis={snap.inputs}
          newApis={snap.inputs.map((a) => a.id)}
          busy={busy === 'retire'}
          onConfirm={(ids) => void retire(ids)}
          onCancel={() => setCandidates(null)}
        />
      ) : (
        <div className="row">
          <Button disabled={busy !== null} onClick={() => void open()}>
            {busy === 'load' ? 'Looking…' : 'Retire older models of this concept'}
          </Button>
          {none ? (
            <span role="status" className="small muted">
              There is no other official model of this concept.
            </span>
          ) : null}
        </div>
      )}
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
    </Card>
  );
}

function releaseError(e: unknown, action: 'release' | 'discard', replacing = false): string {
  return e instanceof ApiError && e.status === 409 && replacing
    ? `Nothing was released: one of the models to replace is no longer an official model of this concept (${e.message}). Reload and choose again.`
    : e instanceof ApiError && e.status === 401
      ? 'Your session is not valid any more. Sign in again.'
      : e instanceof ApiError && e.status === 409
        ? 'This model is not waiting for review any more: someone else released or discarded it. Reload to see its state.'
        : e instanceof ApiError && e.status === 422
          ? `The server refused the replacement: ${e.message}`
          : e instanceof Error
            ? e.message
            : `Could not ${action} the model.`;
}

/** A maintainer reviews an unreleased model, then releases it (official, public) or discards it. */
export function ReviewBanner({
  snap,
  onChanged,
}: {
  snap: ModelSnapshot;
  /** Called with the server's answer (a release names what it replaced). */
  onChanged: (answer?: ModelSnapshot) => void;
}) {
  const client = useApiClient();
  const maintainer = useIsMaintainer();
  const [busy, setBusy] = useState<'release' | 'discard' | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Supersedable[] | null>(null);
  if (snap.visibility !== 'unreleased') return null;
  const warningGroups = groupWarnings(snap.warnings);

  /** Release asks first when official models of the same concept exist; with none it releases at once. */
  async function startRelease() {
    setBusy('release');
    setError(null);
    try {
      const found = await client.listSupersedable(snap.id);
      if (found.length === 0) {
        await client.releaseModel(snap.id);
        onChanged();
        return;
      }
      setCandidates(found);
    } catch (e) {
      setError(releaseError(e, 'release'));
    } finally {
      setBusy(null);
    }
  }

  async function run(action: 'release' | 'discard', supersedes?: string[]) {
    setBusy(action);
    setError(null);
    try {
      const answer =
        action === 'release'
          ? await client.releaseModel(snap.id, undefined, { supersedes })
          : await client.discardModel(snap.id);
      setConfirmDiscard(false);
      setCandidates(null);
      onChanged(answer);
    } catch (e) {
      setError(releaseError(e, action, Boolean(supersedes?.length)));
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
      {warningGroups.length ? (
        <p className="small review-warnings">
          <b>Before you release:</b> {warningGroups.map((g) => g.summary).join('; ')}.{' '}
          <a href={`#${WARNINGS_ID}`}>See the list</a>
        </p>
      ) : null}
      {maintainer ? (
        <div className="row">
          <Button
            variant="primary"
            disabled={busy !== null || candidates !== null}
            onClick={() => void startRelease()}
          >
            {busy === 'release' && candidates === null ? 'Releasing…' : 'Release'}
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
      {candidates ? (
        <ReleaseChoice
          candidates={candidates}
          apis={snap.inputs}
          newApis={snap.inputs.map((a) => a.id)}
          busy={busy === 'release'}
          onConfirm={(supersedes) => void run('release', supersedes)}
          onCancel={() => setCandidates(null)}
        />
      ) : null}
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
    </Banner>
  );
}
