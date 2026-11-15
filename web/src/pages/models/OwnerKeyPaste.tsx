import { useState, type FormEvent } from 'react';
import { useApiClient } from '@/api/context';
import { Button, Card } from '@/components';
import { readOwnerKeys, saveOwnerKey } from '@/lib/ownerKeys';

/**
 * "Have an owner key?": a key from another browser, or from the view in Claude (it is shown there once), lists
 * the models and model sets it belongs to here. The key is checked against the server first (POST, so it never
 * reaches a URL or a log) and only kept in this browser when it finds something: a mistyped key is not stored.
 * It lists; it cannot change or release anything.
 */
export function OwnerKeyPaste({ onAdded }: { onAdded: () => void }) {
  const client = useApiClient();
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    const key = value.trim();
    if (!key) return;
    if (/\s/.test(key)) {
      setMessage({ ok: false, text: 'A key has no spaces: paste only the key.' });
      return;
    }
    if (readOwnerKeys().includes(key)) {
      setMessage({ ok: true, text: 'This browser already has that key.' });
      setValue('');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const [models, sets] = await Promise.all([
        client.listMyModels([key]),
        client.listMyModelSets([key]),
      ]);
      const m = models.items.length;
      const s = sets.items.length;
      if (m + s === 0) {
        setMessage({
          ok: false,
          text: 'No model or model set belongs to this key. Check that you copied all of it.',
        });
        return;
      }
      saveOwnerKey(key);
      setValue('');
      setMessage({
        ok: true,
        text: `Added: ${m} ${m === 1 ? 'model' : 'models'} and ${s} model ${s === 1 ? 'set' : 'sets'} are listed below.`,
      });
      onAdded();
    } catch (err) {
      setMessage({
        ok: false,
        text: err instanceof Error ? err.message : 'Could not check the key.',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="pad owner-key-paste" role="region" aria-label="Add an owner key">
      <details>
        <summary>Have an owner key from another browser or from Claude?</summary>
        <p className="muted small">
          Paste it to list your models and model sets here. It only lists them: it cannot change or
          release anything.
        </p>
        <form onSubmit={add} noValidate className="share-row">
          <label htmlFor="owner-key-input" className="sr-only">
            Owner key
          </label>
          <input
            id="owner-key-input"
            className="input mono"
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Paste your key"
          />
          <Button type="submit" disabled={busy || value.trim() === ''}>
            {busy ? 'Checking…' : 'Add key'}
          </Button>
        </form>
        {message ? (
          <p
            role={message.ok ? 'status' : 'alert'}
            className={`small ${message.ok ? 'ok' : 'form-error'}`}
          >
            {message.text}
          </p>
        ) : null}
      </details>
    </Card>
  );
}
