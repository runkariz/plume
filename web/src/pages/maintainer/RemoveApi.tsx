import { useEffect, useId, useState } from 'react';
import { useApiClient } from '@/api/context';
import { ApiError, type ApiSummary, type PinnedBy, type RemoveApiResult } from '@/api/types';
import { Button, Chip } from '@/components';

const VISIBILITY: Record<PinnedBy['visibility'], string> = {
  official: 'released',
  unreleased: 'unreleased',
};

/** "releaseNotes" -> "release notes": the server's counts are named in camelCase. */
const words = (key: string) => key.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();

/** What was removed, as "12 documents, 3 builds": only the counts above zero. */
export function removedSummary(removed: RemoveApiResult['removed']): string {
  return Object.entries(removed)
    .filter(([key, n]) => typeof n === 'number' && n > 0 && key !== 'api')
    .map(([key, n]) => `${n} ${words(key)}`)
    .join(', ');
}

function Pinned({ items }: { items: PinnedBy[] }) {
  return (
    <ul className="plain remove-pinned" aria-label="Models and sets that use this API">
      {items.map((p) => (
        <li key={`${p.type}-${p.id}`}>
          <Chip>{p.type === 'set' ? 'set' : 'model'}</Chip> <b>{p.name}</b>{' '}
          <span className="faint small">{VISIBILITY[p.visibility] ?? p.visibility}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Removes an API (maintainer) with everything it holds. The id is typed to confirm. Models and sets that use the
 * API are listed first: removing it retires them, so the maintainer has to say so ("force") before the server does it.
 */
export function RemoveApi({
  api,
  onClose,
  onRemoved,
}: {
  api: ApiSummary;
  onClose: () => void;
  onRemoved: (result: RemoveApiResult) => void;
}) {
  const client = useApiClient();
  const uid = useId();
  const [pinned, setPinned] = useState<PinnedBy[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    client.getApiRemoval(api.id, ctl.signal).then(
      (r) => setPinned(r.pinnedBy),
      (e: unknown) => {
        if (ctl.signal.aborted) return;
        setLoadError(e instanceof Error && e.message ? e.message : 'Could not check what uses it.');
      },
    );
    return () => ctl.abort();
  }, [client, api.id]);

  const inUse = pinned !== null && pinned.length > 0;
  const ready = typed === api.id && (!inUse || force) && !busy;

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const result = await client.removeApi(api.id, {
        confirm: typed,
        ...(force ? { force: true } : {}),
        ...(reason.trim() ? { reason: reason.trim() } : {}),
      });
      onRemoved(result);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'api_in_use') {
        // something pinned it since the check: show who, and ask for the force box
        setPinned(e.pinnedBy ?? []);
        setForce(false);
        setError('Models or sets use this API now. Tick the box below to remove it anyway.');
      } else {
        setError(e instanceof Error && e.message ? e.message : 'The API was not removed.');
      }
      setBusy(false);
    }
  }

  return (
    <div className="rollback-confirm remove-api" role="group" aria-label={`Remove ${api.id}`}>
      <p>
        <b>Remove {api.name}?</b> Its documents, builds, tags, release notes, jobs and display name
        are deleted from this server. This cannot be undone: to get it back, load the package again.
      </p>
      {pinned === null && !loadError ? <p className="muted small">Checking what uses it…</p> : null}
      {loadError ? (
        <p role="alert" className="form-error">
          {loadError}
        </p>
      ) : null}
      {inUse ? (
        <>
          <p>
            {pinned.length === 1
              ? 'This model or set uses'
              : `These ${pinned.length} models and sets use`}{' '}
            this API. Removing the API retires {pinned.length === 1 ? 'it' : 'them'}.
          </p>
          <Pinned items={pinned} />
          <label className="remove-force small">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />{' '}
            Remove the API and retire {pinned.length === 1 ? 'it' : `these ${pinned.length}`}
          </label>
        </>
      ) : null}
      <label htmlFor={`${uid}-reason`} className="small">
        Reason (optional, kept with the removal)
      </label>
      <textarea
        id={`${uid}-reason`}
        className="input"
        rows={2}
        maxLength={500}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <label htmlFor={`${uid}-confirm`} className="small">
        Type <span className="mono">{api.id}</span> to confirm
      </label>
      <input
        id={`${uid}-confirm`}
        className="input mono"
        autoComplete="off"
        spellCheck={false}
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
      />
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
      <div className="row">
        <Button variant="primary" disabled={!ready} onClick={() => void remove()}>
          {busy ? 'Removing…' : `Remove ${api.id}`}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** The result of a removal: what was deleted and what was retired. */
export function RemovedNotice({
  result,
  onDismiss,
}: {
  result: RemoveApiResult;
  onDismiss: () => void;
}) {
  const summary = removedSummary(result.removed);
  return (
    <div className="banner ok" role="status">
      <div>
        <h3>
          Removed <span className="mono">{result.api}</span>
        </h3>
        <div className="banner-body">
          {summary ? <p>Deleted {summary}.</p> : null}
          {result.retired.length > 0 ? (
            <>
              <p>Retired {result.retired.length === 1 ? 'one' : result.retired.length}:</p>
              <ul className="plain remove-pinned">
                {result.retired.map((r) => (
                  <li key={`${r.type}-${r.id}`}>
                    <Chip>{r.type === 'set' ? 'set' : 'model'}</Chip> <b>{r.name}</b>{' '}
                    <span className="faint small">now {r.now}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <button type="button" className="linkbtn small" onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
