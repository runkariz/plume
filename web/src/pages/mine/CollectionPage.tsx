import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError } from '@/api/types';
import { Banner, Button, Card, Crumbs, ErrorState, LoadingState } from '@/components';
import { parseCollectionRef, saveCollectionId, useCollectionId } from '@/lib/collection';
import { ModelRows } from '@/pages/models/ModelList';
import { SetRows } from '@/pages/sets/SetLists';
import { CollectionLink } from './CollectionLink';

/**
 * A My models page (/mine/<id>): the models and model sets saved under one link, newest first. It is a list, not an
 * admin key. Opening it does not change this browser; "Use this link here" does, and "Merge my other link into this
 * one" moves what this browser's current link holds into it first.
 */
export function CollectionPage() {
  const { collectionId = '' } = useParams();
  const id = parseCollectionRef(collectionId);
  const client = useApiClient();
  const mine = useCollectionId();
  const load = useCallback(
    (signal: AbortSignal) =>
      id
        ? client.getCollection(id, signal)
        : Promise.reject(new ApiError(404, 'Not a My models link')),
    [client, id],
  );
  const { state, retry } = useAsync(load);
  const [busy, setBusy] = useState<'use' | 'merge' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const crumbs = [{ label: 'Models', to: '/models' }, { label: 'My models' }];

  if (state.status === 'loading')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading My models" />
      </>
    );
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'This My models link is not known here'
              : 'Could not load My models'
          }
          message={
            state.error instanceof ApiError && state.error.status === 404
              ? 'It may be mistyped, or come from another Plume.'
              : state.error.message
          }
          onRetry={retry}
        />
      </>
    );

  const c = state.data;
  const isMine = mine === c.id;
  const other = mine && mine !== c.id ? mine : null;

  async function adoptHere() {
    setBusy('use');
    setError(null);
    saveCollectionId(c.id);
    setDone('This browser uses this link now: what you save from here on is added to it.');
    setBusy(null);
  }
  async function merge() {
    if (!other) return;
    setBusy('merge');
    setError(null);
    try {
      await client.mergeCollection(c.id, [other]);
      saveCollectionId(c.id);
      setDone(
        'Merged: everything from your other link is here now, and this browser uses this link.',
      );
      retry();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 400
          ? 'A My models link holds at most 500 items: nothing was merged.'
          : e instanceof Error && e.message
            ? e.message
            : 'Could not merge.',
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">My models</h1>
          <p className="muted small">
            {c.count} {c.count === 1 ? 'item' : 'items'} saved under this link
            {isMine ? ' · the link of this browser' : ''}
          </p>
        </div>
      </div>
      <div className="mine-stack">
        {c.mergedInto ? (
          <Banner tone="accent" title="This link was merged into another one">
            Its models moved: <Link to={`/mine/${c.mergedInto}`}>open the one they are in now</Link>
            .
          </Banner>
        ) : null}
        <Card className="pad">
          <h2 className="h2-sm">Link to this list</h2>
          <p className="muted small">
            Bookmark it to find these models from any browser. It only lists them: it cannot change
            or release anything.
          </p>
          <CollectionLink id={c.id} />
          {!c.mergedInto && !isMine ? (
            <div className="row" style={{ marginTop: 12 }}>
              <Button onClick={() => void adoptHere()} disabled={busy !== null}>
                Use this link in this browser
              </Button>
              {other ? (
                <Button onClick={() => void merge()} disabled={busy !== null}>
                  {busy === 'merge' ? 'Merging…' : 'Merge my other link into this one'}
                </Button>
              ) : null}
            </div>
          ) : null}
          {done ? (
            <p role="status" className="small ok">
              {done}
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
        </Card>
        {!c.mergedInto ? (
          <>
            <Card className="pad model-list" role="region" aria-label="Models">
              <h2 className="h2-sm">Models</h2>
              {c.models.length ? (
                <ModelRows items={c.models} />
              ) : (
                <p className="muted small">No models yet.</p>
              )}
            </Card>
            <Card className="pad model-list" role="region" aria-label="Model sets">
              <h2 className="h2-sm">Model sets</h2>
              {c.sets.length ? (
                <SetRows items={c.sets} />
              ) : (
                <p className="muted small">No model sets yet.</p>
              )}
            </Card>
          </>
        ) : null}
      </div>
    </>
  );
}
