import type { ReactNode } from 'react';
import type { ConflictStatement, DocConflict } from '@/api/types';
import { safeHref } from '@/pages/maintainer/release/notes';
import { Card } from './Card';
import { Chip } from './Chip';

/** Where a statement stands, in words: "the description", "parameter limit", "page https://...". */
export function placeOf(where: string): { label: string; url: string | null } {
  if (where === 'description') return { label: 'the description', url: null };
  // a page named only by the statement's source link
  if (where === 'page') return { label: 'a documentation page', url: null };
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

const CONDITION = 'condition';

/** A property path names the same field with or without its array marks ("items[].id" and "items.id"). */
const bare = (path: string) => path.toLowerCase().replace(/\[\]/g, '');

/** A name (a field, a one-word limit) is set as code; a limit written as a sentence is plain text. */
function Subject({ text }: { text: string }) {
  return /\s/.test(text) ? <>{text}</> : <span className="mono">{text}</span>;
}

/** One entry: its heading, what the server says it is about, and every statement with its place. */
function Entry({
  c,
  heading,
  about = null,
}: {
  c: DocConflict;
  heading: ReactNode;
  about?: string | null;
}) {
  return (
    <div className="conflict">
      <h3 className="conflict-title">{heading}</h3>
      {about ? <p className="small muted conflict-about">{about}</p> : null}
      <ul className="conflict-list" aria-label={`Statements about ${c.field ?? c.limit}`}>
        {c.statements.map((s, i) => (
          <Statement key={`${s.where}-${i}`} s={s} />
        ))}
      </ul>
    </div>
  );
}

const keyOf = (c: DocConflict, i: number) => `${c.field ?? ''}-${c.limit}-${i}`;

/**
 * What the docs say that a caller has to know about a value. A disagreement: a limit stated with different values,
 * every statement with its place, examples marked, none picked. A condition (kind "condition"): a field is required only
 * in the stated case; that is not a disagreement and is shown apart. Nothing when there are none.
 */
export function DocConflicts({ conflicts }: { conflicts: DocConflict[] | undefined }) {
  const list = (conflicts ?? []).filter((c) => c && c.limit && (c.statements?.length ?? 0) > 0);
  const conditions = list.filter((c) => c.kind === CONDITION);
  const disagreements = list.filter((c) => c.kind !== CONDITION);
  return (
    <>
      {disagreements.length ? (
        <Card className="pad doc-conflicts" role="region" aria-label="Conflicting statements">
          <h2 className="h2-sm">The docs disagree</h2>
          <p className="muted small">
            These are stated with different values. Plume does not pick one: check the vendor.
          </p>
          {disagreements.map((c, i) => (
            <Entry
              key={keyOf(c, i)}
              c={c}
              heading={
                <>
                  The docs state different values for <Subject text={c.field ?? c.limit} />:
                </>
              }
              // what the server calls the limit, when the heading names the field instead
              about={c.field && bare(c.limit) !== bare(c.field) ? c.limit : null}
            />
          ))}
        </Card>
      ) : null}
      {conditions.length ? (
        <Card className="pad doc-conditions" role="region" aria-label="Conditions">
          <h2 className="h2-sm">Conditions</h2>
          <p className="muted small">
            When the docs state these fields are required. They are not a disagreement.
          </p>
          {conditions.map((c, i) => (
            <Entry
              key={keyOf(c, i)}
              c={c}
              heading={
                <>
                  Condition on <Subject text={c.field ?? c.limit} /> (required only in this case):
                </>
              }
            />
          ))}
        </Card>
      ) : null}
    </>
  );
}
