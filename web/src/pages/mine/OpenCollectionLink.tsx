import { useState, type FormEvent } from 'react';
import { useApiClient } from '@/api/context';
import { ApiError } from '@/api/types';
import { Button, Card } from '@/components';
import { parseCollectionRef, saveCollectionId } from '@/lib/collection';

/**
 * "Open another My models link": paste a link (or just its id) from another browser or from Claude. It is checked
 * against the server first, so a mistyped one is not kept; opening it makes it the link of this browser.
 * The result is shown outside the collapsible part and the panel stays open until it works.
 */
export function OpenCollectionLink({ onOpened }: { onOpened: (id: string) => void }) {
  const client = useApiClient();
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setOpen(true);
    if (value.trim() === '') return;
    const id = parseCollectionRef(value);
    if (!id) {
      setMessage({
        ok: false,
        text: 'That is not a My models link. Paste the whole link (…/mine/c-…) or its id (c-…).',
      });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const c = await client.getCollection(id);
      saveCollectionId(c.mergedInto ?? id);
      setValue('');
      setMessage({
        ok: true,
        text: c.mergedInto
          ? 'That link was merged into another one: this browser uses the new one now.'
          : `Opened: ${c.count} ${c.count === 1 ? 'item' : 'items'}. This browser uses that link now.`,
      });
      onOpened(c.mergedInto ?? id);
    } catch (err) {
      setMessage({
        ok: false,
        text:
          err instanceof ApiError && err.status === 404
            ? 'This Plume does not know that link (it may come from another site, or be mistyped).'
            : err instanceof ApiError
              ? `The server refused the check: ${err.message || err.status}.`
              : `Could not reach the Plume API to check the link${err instanceof Error && err.message ? ` (${err.message})` : ''}. It was not opened; try again when the API is reachable.`,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="pad owner-key-paste" role="region" aria-label="Open a My models link">
      <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>Have a My models link from another browser or from Claude?</summary>
        <p className="muted small">
          Paste it to list your models and model sets here. The link only lists them: it cannot
          change or release anything.
        </p>
        <form onSubmit={add} noValidate className="share-row">
          <label htmlFor="collection-link-input" className="sr-only">
            My models link
          </label>
          <input
            id="collection-link-input"
            className="input mono"
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Paste the link"
          />
          <Button type="submit" disabled={busy || value.trim() === ''}>
            {busy ? 'Checking…' : 'Open link'}
          </Button>
        </form>
      </details>
      {message ? (
        <p
          role={message.ok ? 'status' : 'alert'}
          className={`small ${message.ok ? 'ok' : 'form-error'}`}
        >
          {message.text}
        </p>
      ) : null}
    </Card>
  );
}
