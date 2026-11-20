import type { ConflictStatement, DocConflict } from '@/api/types';
import { safeHref } from '@/pages/maintainer/release/notes';
import { Card } from './Card';
import { Chip } from './Chip';

/** Where a statement stands, in words: "the description", "parameter limit", "page https://...". */
export function placeOf(where: string): { label: string; url: string | null } {
  if (where === 'description') return { label: 'the description', url: null };
  if (where.startsWith('param:'))
    return { label: `parameter ${where.slice('param:'.length)}`, url: null };
  if (where.startsWith('page:')) {
    const url = where.slice('page:'.length);
    return { label: 'page', url };
  }
  return { label: where, url: null };
}

function Statement({ s }: { s: ConflictStatement }) {
  const place = placeOf(s.where);
  const href = safeHref(place.url ?? s.sourceUrl);
  return (
    <li className="conflict-statement">
      <q>{s.quote}</q>
      <span className="conflict-place faint small">
        {' '}
        in {place.label}
        {place.url ? (
          <>
            {' '}
            {href ? (
              <a href={href} target="_blank" rel="noreferrer noopener" title={place.url}>
                {place.url}
              </a>
            ) : (
              <span className="mono">{place.url}</span>
            )}
          </>
        ) : null}
        {!place.url && href ? (
          <>
            {' '}
            (
            <a href={href} target="_blank" rel="noreferrer noopener">
              source
            </a>
            )
          </>
        ) : null}
      </span>
      {s.isExample ? <Chip>example</Chip> : null}
    </li>
  );
}

/**
 * The limits the docs state with different values, each with every statement and its place, examples marked. None is
 * picked: they are listed as the server sends them. Nothing when there are none (every package so far).
 */
export function DocConflicts({ conflicts }: { conflicts: DocConflict[] | undefined }) {
  const list = (conflicts ?? []).filter((c) => c && c.limit && (c.statements?.length ?? 0) > 0);
  if (list.length === 0) return null;
  return (
    <Card className="pad doc-conflicts" role="region" aria-label="Conflicting statements">
      <h2 className="h2-sm">The docs disagree</h2>
      <p className="muted small">
        These limits are stated with different values. Plume does not pick one: check the vendor.
      </p>
      {list.map((c) => (
        <div key={c.limit} className="conflict">
          <h3 className="conflict-title">
            The docs state different values for <span className="mono">{c.limit}</span>:
          </h3>
          <ul className="conflict-list" aria-label={`Statements about ${c.limit}`}>
            {c.statements.map((s, i) => (
              <Statement key={`${s.where}-${i}`} s={s} />
            ))}
          </ul>
        </div>
      ))}
    </Card>
  );
}
