import { useState } from 'react';
import { useApiClient } from '@/api/context';
import { ApiError, type ApiSummary } from '@/api/types';
import { Button, Chip } from '@/components';

/**
 * A maintainer renames an API for display (the name the whole app and the model labels use). The package's own name
 * stays behind it: "Use the package name" clears the override and says what that name is. 1 to 80 characters; the
 * server collapses whitespace and refuses an empty or too long name, which is shown as it says it.
 */
export function DisplayNameEditor({ api, onChanged }: { api: ApiSummary; onChanged: () => void }) {
  const client = useApiClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(api.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [packageName, setPackageName] = useState<string | null>(null);

  async function save(next: string | null) {
    setBusy(true);
    setError(null);
    try {
      const r = await client.setApiDisplayName(api.id, next);
      setPackageName(r.packageName);
      setOpen(false);
      onChanged();
    } catch (e) {
      setError(
        e instanceof ApiError && e.message
          ? e.message
          : e instanceof Error && e.message
            ? e.message
            : 'The name was not saved.',
      );
    } finally {
      setBusy(false);
    }
  }

  const label = `Display name of ${api.id}`;
  if (!open)
    return (
      <span className="display-name">
        {api.nameSource === 'override' ? <Chip tone="info">Renamed</Chip> : null}{' '}
        <button
          type="button"
          className="linkbtn small"
          aria-label={`Rename ${api.name}`}
          onClick={() => {
            setName(api.name);
            setError(null);
            setOpen(true);
          }}
        >
          Rename
        </button>
        {packageName && api.nameSource !== 'override' ? (
          <span className="faint small"> (package name: {packageName})</span>
        ) : null}
      </span>
    );
  const trimmed = name.replace(/\s+/g, ' ').trim();
  return (
    <form
      className="display-name-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (trimmed) void save(trimmed);
      }}
    >
      <label className="small" htmlFor={`dn-${api.id}`}>
        {label}
      </label>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <input
          id={`dn-${api.id}`}
          className="input"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          aria-describedby={error ? `dn-err-${api.id}` : undefined}
        />
        <Button type="submit" variant="primary" disabled={busy || !trimmed || trimmed === api.name}>
          {busy ? 'Saving…' : 'Save name'}
        </Button>
        <Button disabled={busy} onClick={() => setOpen(false)}>
          Cancel
        </Button>
        {api.nameSource === 'override' ? (
          <Button disabled={busy} onClick={() => void save(null)}>
            Use the package name
          </Button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" id={`dn-err-${api.id}`} className="form-error small">
          {error}
        </p>
      ) : null}
    </form>
  );
}
