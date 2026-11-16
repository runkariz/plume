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
 * A list of changes shown 50 at a time (a real Shopify run has thousands; rendering them all would freeze the page),
 * filtered by the page's filter text.
 */
export function PagedChanges({
  api,
  build,
  items,
  query,
  onChanged,
  label,
}: {
  api: string;
  build: string;
  items: ChangeItem[];
  query: string;
  onChanged: () => void;
  label: string;
}) {
  const [shown, setShown] = useState(STEP);
  const found = useMemo(() => items.filter((i) => matches(i, query)), [items, query]);
  const visible = found.slice(0, shown);
  return (
    <>
      {query.trim() && found.length !== items.length ? (
        <p className="faint small" role="status">
          {found.length} of {items.length} match “{query.trim()}”.
        </p>
      ) : null}
      <ul className="plain change-list" aria-label={label}>
        {visible.map((i) => (
          <ChangeRow key={i.id} api={api} build={build} item={i} onChanged={onChanged} />
        ))}
      </ul>
      {found.length > shown ? (
        <p>
          <Button onClick={() => setShown((n) => n + STEP)}>
            Show {Math.min(STEP, found.length - shown)} more ({found.length - shown} left)
          </Button>
        </p>
      ) : null}
      {found.length === 0 && items.length > 0 ? (
        <p className="muted small">Nothing matches.</p>
      ) : null}
    </>
  );
}
