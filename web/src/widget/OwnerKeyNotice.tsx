import { useRef, useState } from 'react';
import { Banner, Button } from '@/components';

/**
 * The owner key of a model or set someone without a maintainer token just made. The server sends it once, only in
 * `structuredContent.owner_key` (the tool text points here), so this notice is the only place to get it. It lists
 * "Your models" on Plume's Models page from any browser. It is kept in memory only: no storage, no URL, no log.
 *
 * A sandboxed frame may refuse the clipboard API, so Copy falls back to selecting the key (and the browser's copy
 * command); if that fails too the key stays selected for the person to copy by hand.
 */
export function OwnerKeyNotice({
  ownerKey,
  what,
}: {
  ownerKey: string;
  what: 'model' | 'model set';
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
      await navigator.clipboard.writeText(ownerKey);
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

  return (
    <Banner tone="accent" title={`Your ${what} is saved, and unlisted`}>
      <p>
        Only people with the link can open it. Keep this key to find or list your {what}s later
        (paste it in <b>Your models</b> on Plume&apos;s Models page):
      </p>
      <div className="widget-key">
        <label htmlFor="owner-key" className="sr-only">
          Owner key
        </label>
        <input
          id="owner-key"
          ref={field}
          className="input mono"
          readOnly
          value={ownerKey}
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button onClick={() => void copy()}>Copy key</Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Dismiss
        </Button>
      </div>
      <span role="status" className="faint small">
        {state === 'ok'
          ? 'Key copied'
          : state === 'fail'
            ? 'Copy failed: the key is selected, copy it by hand'
            : ''}
      </span>
    </Banner>
  );
}
