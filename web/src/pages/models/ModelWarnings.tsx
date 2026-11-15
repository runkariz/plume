import { Link } from 'react-router-dom';
import type { ModelSnapshot } from '@/api/types';
import { Banner } from '@/components';
import { groupWarnings, warningSearch, WARNINGS_ID } from './warnings';

/**
 * What the server noticed about the mappings of a model but did not refuse (a warning, not an error): one block per
 * kind, each with the mappings it is about, linked to the mapping detail. All text is the server's own, as text.
 */
export function ModelWarnings({ snap }: { snap: ModelSnapshot }) {
  const groups = groupWarnings(snap.warnings);
  if (groups.length === 0) return null;
  return (
    <div id={WARNINGS_ID} className="model-warnings">
      <Banner tone="warn" title="Check these mappings">
        {groups.map((g) => (
          <section key={g.code} aria-label={g.summary} className="warning-group">
            <p>
              <b>{g.summary}</b>
            </p>
            <ul className="plain">
              {g.items.map((w, i) => {
                const search = warningSearch(snap, w);
                return (
                  <li key={`${w.field ?? ''}-${w.api ?? ''}-${i}`}>
                    {search ? (
                      <Link to={search} className="mono">
                        {w.field}
                      </Link>
                    ) : w.field ? (
                      <span className="mono">{w.field}</span>
                    ) : null}
                    {w.api ? (
                      <span className="faint small">
                        {' '}
                        ({snap.inputs.find((a) => a.id === w.api)?.shortName ?? w.api})
                      </span>
                    ) : null}
                    {w.message ? <div className="small muted">{w.message}</div> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </Banner>
    </div>
  );
}
