import { docHref } from '@/lib/docHref';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { FieldSupport, ModelField, ModelSnapshot } from '@/api/types';
import { Chip } from '@/components';

const SUPPORT_LABEL: Record<FieldSupport, string> = {
  supported: 'direct',
  derived: 'derived',
  unsupported: 'not supported',
};
const SUPPORT_TONE = { supported: 'ok', derived: 'warn', unsupported: 'neutral' } as const;

export { docHref };

function matches(f: ModelField, q: string): boolean {
  if (!q) return true;
  const hay = [
    f.name,
    f.description ?? '',
    ...Object.values(f.sources).flatMap((s) => s.paths.map((p) => p.path)),
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

function hasGap(f: ModelField, snap: ModelSnapshot): boolean {
  return snap.inputs.some((a) => (f.support[a.id] ?? 'unsupported') === 'unsupported');
}

/**
 * The readable view of a model: one row per canonical field, one column per API, with how each API fills it
 * (direct / derived / not supported), the source paths, the transform and join, and the citations behind it.
 * It is the primary view for big models; the graph is the overview.
 */
export function MappingTable({ snapshot }: { snapshot: ModelSnapshot }) {
  const [query, setQuery] = useState('');
  const [gapsOnly, setGapsOnly] = useState(false);
  const q = query.trim().toLowerCase();
  const rows = useMemo(
    () => snapshot.fields.filter((f) => matches(f, q) && (!gapsOnly || hasGap(f, snapshot))),
    [snapshot, q, gapsOnly],
  );

  return (
    <div className="mtable">
      <div className="mtable-controls">
        <div>
          <label htmlFor="table-filter" className="sr-only">
            Filter fields
          </label>
          <input
            id="table-filter"
            type="search"
            className="input"
            placeholder="Filter by field name, description or source path"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="pillf"
          aria-pressed={gapsOnly}
          onClick={() => setGapsOnly((v) => !v)}
        >
          Only fields with gaps
        </button>
        <span className="faint small" aria-live="polite">
          {rows.length} of {snapshot.fields.length} fields
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="muted state">No field matches this filter.</p>
      ) : (
        <table className="mtable-grid">
          <caption className="sr-only">
            How each API fills each field of the {snapshot.name} model
          </caption>
          <thead>
            <tr>
              <th scope="col">Field</th>
              {snapshot.inputs.map((a) => (
                <th scope="col" key={a.id}>
                  {a.shortName}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.name}>
                <th scope="row" className="mtable-field">
                  <span className="mono mtable-name">{f.name}</span>
                  <span className="faint small">
                    <span className="mono">{f.type}</span>
                    {f.required ? <span className="chip acc ev-req">required</span> : null}
                  </span>
                  {f.description ? <span className="muted small">{f.description}</span> : null}
                </th>
                {snapshot.inputs.map((a) => {
                  const support = f.support[a.id] ?? 'unsupported';
                  const src = f.sources[a.id];
                  return (
                    <td key={a.id} data-label={a.shortName}>
                      <Chip tone={SUPPORT_TONE[support]}>{SUPPORT_LABEL[support]}</Chip>
                      {src && support !== 'unsupported' ? (
                        <>
                          <div className="mono mtable-path">
                            {src.paths.map((p) => p.path).join(', ')}
                          </div>
                          {src.transform ? (
                            <div className="small muted">
                              <span className="faint">transform:</span> {src.transform}
                            </div>
                          ) : null}
                          {src.join?.length ? (
                            <div className="small muted">
                              <span className="faint">join:</span> {src.join.join('; ')}
                            </div>
                          ) : null}
                          {src.fetch ? (
                            <div className="small muted mono">{src.fetch.endpoint}</div>
                          ) : null}
                          {src.evidence?.length ? (
                            <details className="mtable-cites">
                              <summary>
                                {src.evidence.length} citation{src.evidence.length === 1 ? '' : 's'}
                              </summary>
                              <ul>
                                {src.evidence.map((e, i) => (
                                  <li key={`${e.docId ?? ''}-${i}`}>
                                    <q>{e.quote}</q>
                                    {e.docId ? (
                                      <>
                                        {' '}
                                        <Link className="small" to={docHref(a.id, e.docId)}>
                                          {e.docId}
                                        </Link>
                                      </>
                                    ) : null}
                                  </li>
                                ))}
                              </ul>
                            </details>
                          ) : null}
                        </>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
