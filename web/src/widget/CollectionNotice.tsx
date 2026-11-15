import { useRef, useState } from 'react';
import type { CollectionRef } from '@/api/types';
import { Banner, Button } from '@/components';

/**
 * The My models link of someone without a maintainer token who just saved a model or set: "Your models: <link>".
 * The server sends it in `structuredContent.collection` (the tool text says it is in the view). It lists their models
 * from any browser: bookmark it. It is a list, not a key, but it is still the person's own link, so it is only text in
 * this view: no storage, no request. When the server says something about it (`note`, e.g. a link that was not
 * known so a new one was made) the note is shown.
 *
 * A sandboxed frame may refuse the clipboard API, so Copy falls back to selecting the link (and the browser's copy
 * command); if that fails too the link stays selected for the person to copy by hand.
 */
export function CollectionNotice({
  collection,
  what,
  onOpen,
}: {
  collection: CollectionRef;
  what: 'model' | 'model set';
  /** Opens the link through the host (only offered when the host can and the link is absolute). */
  onOpen?: (url: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  const field = useRef<HTMLInputElement>(null);
  if (!open) return null;

  async function copy() {
    const input = field.current;
    input?.focus();
    input?.select();
    let ok = false;
    try {
      await navigator.clipboard.writeText(collection.url);
      ok = true;
    } catch {
      try {
        ok = document.execCommand('copy');
      } catch {
        ok = false;
      }
    }
    setState(ok ? 'ok' : 'fail');
    setTimeout(() => setState('idle'), 3500);
  }

  const absolute = /^https?:\/\//i.test(collection.url);
  return (
    <Banner tone="accent" title={`Your ${what} is saved, and unlisted`}>
      <p>
        Only people with the link to it can open it. <b>Your models:</b>{' '}
        {collection.created
          ? `this is a new link that lists them. Bookmark it to find them later, from any browser.`
          : `it is saved in your My models list. Bookmark the link to find it later, from any browser.`}
      </p>
      {collection.note ? <p className="small">{collection.note}</p> : null}
      <div className="widget-key">
        <label htmlFor="my-models-link" className="sr-only">
          Link to My models
        </label>
        <input
          id="my-models-link"
          ref={field}
          className="input mono"
          readOnly
          value={collection.url}
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button onClick={() => void copy()}>Copy link</Button>
        {onOpen && absolute ? (
          <Button onClick={() => onOpen(collection.url)}>Open My models</Button>
        ) : null}
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Dismiss
        </Button>
      </div>
      <span role="status" className="faint small">
        {state === 'ok'
          ? 'Link copied'
          : state === 'fail'
            ? 'Copy failed: the link is selected, copy it by hand'
            : ''}
      </span>
    </Banner>
  );
}
