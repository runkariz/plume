import { docHref } from '@/lib/docHref';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { FieldSupport, ModelField, ModelSnapshot } from '@/api/types';
import { countLeaves, flatten, hasOwnSources, type FlatField } from './fields';
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
    f.path ?? '',
    ...Object.values(f.sources ?? {}).flatMap((s) => s.paths.map((p) => p.path)),
  ]
    .join(' ')
    .toLowerCase();
  return hay.includes(q);
}

function hasGap(f: ModelField, snap: ModelSnapshot): boolean {
  return snap.inputs.some((a) => (f.support?.[a.id] ?? 'unsupported') === 'unsupported');
}

/**
 * The readable view of a model: one row per canonical field, one column per API, with how each API fills it
 * (direct / derived / not supported), the source paths, the transform and join, and the citations behind it.
 * It is the primary view for big models; the graph is the overview.
 */
export function MappingTable({ snapshot }: { snapshot: ModelSnapshot }) {
  const [query, setQuery] = useState('');
  const [gapsOnly, setGapsOnly] = useState(false);
  // containers (objects and arrays with sub-fields) that the person collapsed; all are open to start with
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const q = query.trim().toLowerCase();
  const all = useMemo(() => flatten(snapshot.fields), [snapshot]);
  const filtering = q !== '' || gapsOnly;
  const rows = useMemo(() => {
    // a matching field keeps its parents on screen (and open), so it is seen in its place
    const keep = new Set<string>();
    for (const x of all) {
      const own = !x.container || hasOwnSources(x.field);
      if (own && matches(x.field, q) && (!gapsOnly || hasGap(x.field, snapshot))) {
        keep.add(x.path);
        for (let p = x.parent; p; p = all.find((y) => y.path === p)?.parent ?? null) keep.add(p);
      }
    }
    const hidden = (x: FlatField) => {
      for (let p = x.parent; p; p = all.find((y) => y.path === p)?.parent ?? null)
        if (collapsed.has(p)) return true;
      return false;
    };
    return all.filter((x) => (filtering ? keep.has(x.path) : !hidden(x)));
  }, [all, snapshot, q, gapsOnly, filtering, collapsed]);
  const leavesShown = rows.filter((x) => !x.container).length;
  const toggle = (path: string) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

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
          {leavesShown} of {countLeaves(snapshot)} fields
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
            {rows.map(({ field: f, path, depth, container }) => (
              <tr key={path} className={depth > 0 ? 'nested' : undefined}>
                <th
                  scope="row"
                  className="mtable-field"
                  style={depth > 0 ? { paddingLeft: 12 + depth * 18 } : undefined}
                >
                  <span className="mono mtable-name">
                    {container ? (
                      <button
                        type="button"
                        className="mtable-toggle"
                        aria-expanded={filtering ? true : !collapsed.has(path)}
                        aria-label={`${collapsed.has(path) && !filtering ? 'Expand' : 'Collapse'} ${path}`}
                        disabled={filtering}
                        onClick={() => toggle(path)}
                      >
                        <span aria-hidden>{filtering || !collapsed.has(path) ? '▾' : '▸'}</span>
                      </button>
                    ) : null}
                    {f.name}
                  </span>
                  {depth > 0 ? (
                    <span className="faint small mono mtable-path-line">{path}</span>
                  ) : null}
                  <span className="faint small">
                    <span className="mono">{f.type}</span>
                    {f.required ? <span className="chip acc ev-req">required</span> : null}
                  </span>
                  {f.description ? <span className="muted small">{f.description}</span> : null}
                </th>
                {snapshot.inputs.map((a) => {
                  const support = f.support?.[a.id] ?? 'unsupported';
                  const src = f.sources?.[a.id];
                  return (
                    <td key={a.id} data-label={a.shortName}>
                      <Chip tone={SUPPORT_TONE[support]}>{SUPPORT_LABEL[support]}</Chip>
                      {container && !hasOwnSources(f) && support !== 'unsupported' ? (
                        <div className="small muted">from its sub-fields</div>
                      ) : null}
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
