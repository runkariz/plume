import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError } from '@/api/types';
import { Button, Card } from '@/components';
import { forgetCollection, saveCollectionId, useCollectionId } from '@/lib/collection';
import { forgetOwnerKeys, readOwnerKeys } from '@/lib/ownerKeys';
import { ModelRows } from '@/pages/models/ModelList';
import { SetRows } from '@/pages/sets/SetLists';
import { CollectionLink } from './CollectionLink';
import { OpenCollectionLink } from './OpenCollectionLink';

/**
 * Old owner keys become the My models link they turned into, once: the server answers `collections` for the keys, this
 * browser keeps that link (any further ones are merged into it) and forgets the keys. A failure changes nothing: the
 * keys stay for the next visit.
 */
function useLegacyKeys(onDone: () => void) {
  const client = useApiClient();
  const current = useCollectionId();
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return;
    const keys = readOwnerKeys();
    if (keys.length === 0) return;
    ran.current = true;
    void (async () => {
      try {
        const { collections = [] } = await client.listMyModels(keys);
        if (collections.length === 0) return;
        const target = current ?? collections[0]?.id;
        if (!target) return;
        const others = collections.map((c) => c.id).filter((id) => id !== target);
        if (others.length) await client.mergeCollection(target, others);
        saveCollectionId(target);
        forgetOwnerKeys();
        onDone();
      } catch {
        /* the keys stay: try again next time */
      }
    })();
  }, [client, current, onDone]);
}

/**
 * "Your models" on /models: what is in the My models link this browser holds, with the link (to bookmark) and a way to
 * open another one. Without a link only the "open a link" control shows.
 */
export function MyModels() {
  const client = useApiClient();
  const id = useCollectionId();
  const [version, setVersion] = useState(0);
  useLegacyKeys(useCallback(() => setVersion((n) => n + 1), []));
  const load = useCallback(
    async (signal: AbortSignal) => (id ? client.getCollection(id, signal) : null),
    [client, id, version], // eslint-disable-line react-hooks/exhaustive-deps -- a new link or a transition reloads it
  );
  const { state, retry } = useAsync(load);
  const data = state.status === 'ready' ? state.data : null;

  // a link that was merged into another: follow it
  const merged = data?.mergedInto ?? null;
  useEffect(() => {
    if (merged) saveCollectionId(merged);
  }, [merged]);

  const unknown =
    state.status === 'error' && state.error instanceof ApiError && state.error.status === 404;
  return (
    <>
      <OpenCollectionLink onOpened={() => setVersion((n) => n + 1)} />
      {id && state.status === 'error' ? (
        <Card className="pad model-list" role="region" aria-label="Your models">
          <h2 className="h2-sm">Your models</h2>
          {unknown ? (
            <>
              <p role="alert" className="form-error">
                This Plume does not know the My models link this browser holds (it may come from
                another site).
              </p>
              <Button onClick={() => forgetCollection()}>Forget that link</Button>
            </>
          ) : (
            <>
              <p role="alert" className="form-error">
                Could not load your models: {state.error.message || 'the API did not answer'}.
              </p>
              <Button onClick={retry}>Try again</Button>
            </>
          )}
        </Card>
      ) : null}
      {data && !merged ? (
        <>
          <Card className="pad model-list" role="region" aria-label="Your models">
            <h2 className="h2-sm">Your models</h2>
            <p className="muted small">
              Everything you saved without signing in, from this browser or any other that has this
              link. Only people with a model's own link can open it.
            </p>
            {data.models.length ? <ModelRows items={data.models} /> : null}
            {data.models.length === 0 && data.sets.length === 0 ? (
              <p className="muted small">Nothing saved yet.</p>
            ) : null}
            <CollectionLink id={data.id} />
            <p className="small">
              <Link to={`/mine/${data.id}`}>Open the My models page</Link>
            </p>
          </Card>
          {data.sets.length ? (
            <Card className="pad model-list" role="region" aria-label="Your model sets">
              <h2 className="h2-sm">Your model sets</h2>
              <SetRows items={data.sets} />
            </Card>
          ) : null}
        </>
      ) : null}
    </>
  );
}
