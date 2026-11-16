import { useMemo, useState } from 'react';
import type { ChangeItem } from '@/api/types';
import { Button } from '@/components';
import { ChangeRow } from './ChangeRow';
import { subjectText } from './notes';

const STEP = 50;

/** Does a change match what the maintainer typed (path, field, model, document)? Case-insensitive, plain text. */
export function matches(i: ChangeItem, q: string): boolean {
  const t = q.trim().toLowerCase();
  if (!t) return true;
  return [subjectText(i), i.subject.fieldPath, i.subject.docId, i.subject.model, i.op, i.kind]
    .filter((x): x is string => Boolean(x))
    .some((x) => x.toLowerCase().includes(t));
}

/**
 * A list of changes shown 50 at a time (a real Shopify run has thousands: rendering them all would freeze the page),
 * filtered by the page's filter text. A report group arrives with only its first 50: `total` is how many there are,
 * and `loadMore(n)` / `loadAll()` fetch the rest from the server on demand. A filter can only look through what is
 * loaded, and says so, with a way to load the rest.
 */
export function PagedChanges({
  api,
  build,
  items,
  query,
  onChanged,
  label,
  total,
  loadMore,
  loadAll,
}: {
  api: string;
  build: string;
  items: ChangeItem[];
  query: string;
  onChanged: () => void;
  label: string;
  /** How many there are in all (more than `items` while the rest is on the server). */
  total?: number;
  loadMore?: (limit: number) => Promise<void>;
  loadAll?: () => Promise<void>;
}) {
  const [shown, setShown] = useState(STEP);
  const [busy, setBusy] = useState(false);
  const found = useMemo(() => items.filter((i) => matches(i, query)), [items, query]);
  const all = total ?? items.length;
  const remote = all > items.length;
  const filtering = query.trim() !== '';
  const visible = found.slice(0, shown);

  async function showMore() {
    setBusy(true);
    try {
      const want = shown + STEP;
      if (!filtering && remote && loadMore && items.length < want)
        await loadMore(want - items.length);
      setShown(want);
    } finally {
      setBusy(false);
    }
  }

  const left = filtering ? found.length - shown : all - shown;
  return (
    <>
      {filtering ? (
        <p className="faint small" role="status">
          {found.length} of {items.length} loaded match “{query.trim()}”.
          {remote ? ` ${all - items.length} more are not loaded yet.` : ''}
        </p>
      ) : null}
      <ul className="plain change-list" aria-label={label}>
        {visible.map((i) => (
          <ChangeRow key={i.id} api={api} build={build} item={i} onChanged={onChanged} />
        ))}
      </ul>
      {left > 0 ? (
        <p>
          <Button disabled={busy} onClick={() => void showMore()}>
            {busy ? 'Loading…' : `Show ${Math.min(STEP, left)} more (${left} left)`}
          </Button>
        </p>
      ) : null}
      {filtering && remote && loadAll ? (
        <p>
          <Button
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void loadAll().finally(() => setBusy(false));
            }}
          >
            {busy ? 'Loading…' : `Load the other ${all - items.length} to search them too`}
          </Button>
        </p>
      ) : null}
      {found.length === 0 && items.length > 0 ? (
        <p className="muted small">Nothing matches.</p>
      ) : null}
    </>
  );
}
