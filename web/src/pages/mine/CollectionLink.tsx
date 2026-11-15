import { useState } from 'react';
import { Button } from '@/components';
import { collectionLink } from '@/lib/collection';

/** The link to a My models collection in a read-only field, with Copy. It lists models: it is not a key. */
export function CollectionLink({
  id,
  label = 'Link to My models',
}: {
  id: string;
  label?: string;
}) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  const link = collectionLink(id);
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setState('ok');
    } catch {
      setState('fail');
    }
    setTimeout(() => setState('idle'), 2500);
  }
  return (
    <div className="collection-link">
      <div className="share-row">
        <label htmlFor={`collection-link-${id}`} className="sr-only">
          {label}
        </label>
        <input
          id={`collection-link-${id}`}
          className="input mono"
          readOnly
          value={link}
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button onClick={() => void copy()}>Copy link</Button>
      </div>
      <span role="status" className="faint small">
        {state === 'ok'
          ? 'Link copied'
          : state === 'fail'
            ? 'Copy failed: select the link instead'
            : ''}
      </span>
    </div>
  );
}
