import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ApiRef, Supersedable } from '@/api/types';
import { Button, Chip } from '@/components';

/** The API ids of `candidate` that the new model does not cover (all covered: the new model loses no API). */
function uncovered(c: Supersedable, newApis: string[]): string[] {
  return c.covered === true ? [] : c.apis.filter((a) => !newApis.includes(a));
}

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
  busy: boolean;
  basePath?: string;
  onConfirm: (supersedes: string[]) => void;
  onCancel: () => void;
}) {
  const legend = useId();
  const [picked, setPicked] = useState<string[]>([]);
  const name = (id: string) => apis.find((a) => a.id === id)?.shortName ?? id;
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const dropped = [
    ...new Set(
      candidates.filter((c) => picked.includes(c.id)).flatMap((c) => uncovered(c, newApis)),
    ),
  ];
  return (
    <fieldset className="release-choice" aria-labelledby={legend}>
      <legend id={legend}>
        <b>Does this {what} replace an official one?</b>
      </legend>
      <p className="small muted">
        These official {what}s are for the same concept. Tick the ones this {what} replaces: they
        will show “Superseded by” this one and leave the lists (they stay readable by their id).
        Nothing is ticked for you.
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
                <b>{c.name}</b> <span className="mono small faint">{c.id}</span>
              </label>
              <div className="release-meta small">
                <span className="muted">{c.apis.map(name).join(', ') || 'no APIs listed'}</span>
                {c.version ? <Chip>v{c.version}</Chip> : null}
                {c.stale ? <Chip tone="warn">stale</Chip> : null}
                {missing.length === 0 ? (
                  <Chip tone="ok">covered by this {what}</Chip>
                ) : (
                  <Chip tone="warn">not covered: {missing.map(name).join(', ')}</Chip>
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
        <Button variant="primary" disabled={busy} onClick={() => onConfirm(picked)}>
          {busy
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
