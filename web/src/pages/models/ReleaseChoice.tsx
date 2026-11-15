import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ApiRef, Supersedable } from '@/api/types';
import { Button, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { apiLabel } from '@/lib/names';

/** The API ids of `candidate` that the new model does not cover, by what the model's APIs say. */
function uncovered(c: Supersedable, newApis: string[]): string[] {
  return c.apis.filter((a) => !newApis.includes(a));
}

/** The server's word wins (`covered`); without it, covered means no API is missing. */
const isCovered = (c: Supersedable, newApis: string[]) =>
  c.covered ?? uncovered(c, newApis).length === 0;

/**
 * Asked when releasing a model that has official models of the same concept: which of them does it replace? None is
 * ticked for the maintainer. Each is shown with the APIs it covers, whether it is built on older docs (stale) and
 * whether the new model covers all its APIs; replacing one that covers an API the new one lacks takes that API out
 * of the official lists, so it says so. Replaced models stay readable by id ("Superseded by ...") but leave the lists.
 */
export function ReleaseChoice({
  candidates,
  apis,
  newApis,
  what = 'model',
  mode = 'release',
  busy,
  basePath = '/models',
  onConfirm,
  onCancel,
}: {
  candidates: Supersedable[];
  /** Names for API ids. */
  apis: ApiRef[];
  /** The API ids the model being released covers. */
  newApis: string[];
  what?: string;
  /** "release": asked while releasing, none ticked is fine. "retire": from an official model's page, at least one. */
  mode?: 'release' | 'retire';
  busy: boolean;
  basePath?: string;
  onConfirm: (supersedes: string[]) => void;
  onCancel: () => void;
}) {
  const legend = useId();
  const [picked, setPicked] = useState<string[]>([]);
  // an API the new model does not cover is not among its inputs: name it from its id
  const name = (id: string) => {
    const known = apis.find((a) => a.id === id);
    return known ? apiLabel(known) : apiLabel({ id });
  };
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const dropped = [
    ...new Set(
      candidates
        .filter((c) => picked.includes(c.id) && !isCovered(c, newApis))
        .flatMap((c) => uncovered(c, newApis)),
    ),
  ];
  return (
    <fieldset className="release-choice" aria-labelledby={legend}>
      <legend id={legend}>
        <b>
          {mode === 'retire'
            ? `Retire older ${what}s of this concept`
            : `Does this ${what} replace an official one?`}
        </b>
      </legend>
      <p className="small muted">
        These official {what}s are for the same concept. Tick the ones{' '}
        {mode === 'retire' ? 'to retire' : `this ${what} replaces`}: they will show “Superseded by”
        this one and leave the lists (they stay readable by their id). Nothing is ticked for you.
      </p>
      <ul className="plain release-candidates">
        {candidates.map((c) => {
          const missing = uncovered(c, newApis);
          const id = `supersede-${c.id}`;
          return (
            <li key={c.id} className={picked.includes(c.id) ? 'on' : undefined}>
              <input
                id={id}
                type="checkbox"
                className="check"
                checked={picked.includes(c.id)}
                disabled={busy}
                onChange={() => toggle(c.id)}
              />
              <label htmlFor={id}>
                <b>{c.name ?? c.concept ?? 'Model'}</b>{' '}
                {c.version ? <span className="small faint">v{c.version} </span> : null}
                {c.createdAt ? (
                  <span className="small faint">{formatDate(c.createdAt)} </span>
                ) : null}
                <span className="mono small faint">{c.id}</span>
              </label>
              <div className="release-meta small">
                <span className="muted">{c.apis.map(name).join(', ') || 'no APIs listed'}</span>
                {c.version ? <Chip>v{c.version}</Chip> : null}
                {c.stale ? <Chip tone="warn">stale</Chip> : null}
                {isCovered(c, newApis) ? (
                  <Chip tone="ok">covered by this {what}</Chip>
                ) : (
                  <Chip tone="warn">
                    not covered{missing.length ? `: ${missing.map(name).join(', ')}` : ''}
                  </Chip>
                )}
                <Link to={`${basePath}/${c.id}`} target="_blank" rel="noreferrer" className="small">
                  Open
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
      {dropped.length ? (
        <p role="status" className="small form-error">
          Replacing a {what} that covers {dropped.map(name).join(', ')} takes{' '}
          {dropped.length === 1 ? 'that API' : 'those APIs'} out of the official lists: this {what}{' '}
          does not cover {dropped.length === 1 ? 'it' : 'them'}.
        </p>
      ) : null}
      <div className="row">
        <Button
          variant="primary"
          disabled={busy || (mode === 'retire' && picked.length === 0)}
          onClick={() => onConfirm(picked)}
        >
          {mode === 'retire'
            ? busy
              ? 'Retiring…'
              : picked.length
                ? `Retire ${picked.length}`
                : 'Retire'
            : busy
              ? 'Releasing…'
              : picked.length
                ? `Release and replace ${picked.length}`
                : 'Release without replacing any'}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </fieldset>
  );
}
