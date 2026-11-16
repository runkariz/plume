import { useState } from 'react';
import type { ApiRateLimit, EndpointRateLimit, RateLimitGroup } from '@/api/types';
import { Card } from './Card';

/** A verbatim scalar of a package as text; anything else is not guessed at. */
const t = (v: unknown): string =>
  typeof v === 'string' || typeof v === 'number' ? String(v).trim() : '';

/** "5 per 60 s", "5 requests", or "": what the package's numbers say, nothing added. */
function amount(g: RateLimitGroup): string {
  const limit = t(g.limit);
  const window = t(g.windowSeconds);
  if (limit && window) return `${limit} per ${window} s`;
  if (limit) return limit;
  if (window) return `window ${window} s`;
  return '';
}

function headers(v: ApiRateLimit['headerNames']): string[] {
  if (Array.isArray(v)) return v.map(t).filter(Boolean);
  const one = t(v);
  return one ? [one] : [];
}

const FIRST = 8;

/**
 * How an API limits calls: a table with one row per entry of the package's rateLimits (Amazon has one per operation),
 * the first few shown and the rest behind a button. A column appears only when some entry says something there, and
 * the headers that report the limits are named once. Nothing is shown when the package has none.
 */
export function RateLimitsCard({ limits }: { limits: ApiRateLimit[] | undefined }) {
  const [all, setAll] = useState(false);
  if (!limits || limits.length === 0) return null;
  const shown = all ? limits : limits.slice(0, FIRST);
  // what every entry shares is said once above the table; what differs goes under its group
  const same = (f: (l: ApiRateLimit) => string): string => {
    const first = f(limits[0] as ApiRateLimit);
    return first !== '' && limits.every((l) => f(l) === first) ? first : '';
  };
  const scope = same((l) => t(l.scope));
  const algorithm = same((l) => t(l.algorithm));
  const showGroup = limits.some((l) => t(l.group));
  const showAmount = limits.some((l) => amount(l));
  const hs = [...new Set(limits.flatMap((l) => headers(l.headerNames)))];
  const detail = (l: ApiRateLimit) =>
    [scope ? '' : t(l.scope), algorithm ? '' : t(l.algorithm), t(l.notes)]
      .filter(Boolean)
      .join(' · ');
  return (
    <Card className="pad rate-limits" role="region" aria-label="Rate limits">
      <h2 style={{ marginBottom: 8 }}>
        Rate limits <span className="faint small">({limits.length})</span>
      </h2>
      {scope || algorithm ? (
        <p className="small muted" style={{ marginBottom: 8 }}>
          {[scope && `Per ${scope}`, algorithm].filter(Boolean).join(' · ')}
        </p>
      ) : null}
      <table className="rl-table">
        <caption className="sr-only">Rate limits</caption>
        <thead>
          <tr>
            <th scope="col">{showGroup ? 'Group' : 'Entry'}</th>
            {showAmount ? <th scope="col">Limit</th> : null}
          </tr>
        </thead>
        <tbody>
          {shown.map((l, i) => (
            <tr key={`${t(l.scope)}-${t(l.group)}-${i}`}>
              <th scope="row">
                {t(l.group) ? <span className="mono">{t(l.group)}</span> : null}
                {detail(l) ? <div className="small muted rl-detail">{detail(l)}</div> : null}
              </th>
              {showAmount ? <td className="rl-amount">{amount(l)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
      {limits.length > FIRST ? (
        <div className="show-all">
          <button type="button" className="linkbtn" onClick={() => setAll(!all)}>
            {all ? `Show the first ${FIRST}` : `Show all ${limits.length}`}
          </button>
        </div>
      ) : null}
      {hs.length > 0 ? (
        <p className="small muted" style={{ marginTop: 10 }}>
          Reported in{' '}
          {hs.map((h, j) => (
            <span key={h}>
              {j > 0 ? ', ' : ''}
              <span className="mono">{h}</span>
            </span>
          ))}
        </p>
      ) : null}
    </Card>
  );
}

/** The limit of one endpoint: its bucket, what a call costs and the group it counts in. Null shows nothing. */
export function EndpointRateLimitCard({ limit }: { limit: EndpointRateLimit | null | undefined }) {
  if (!limit) return null;
  const g = limit.group ?? null;
  const parts = [
    t(limit.bucket) ? { label: 'Bucket', value: t(limit.bucket), mono: true } : null,
    t(limit.cost) ? { label: 'Cost per call', value: t(limit.cost), mono: false } : null,
    g && t(g.group) ? { label: 'Group', value: t(g.group), mono: true } : null,
    g && amount(g) ? { label: 'Limit', value: amount(g), mono: false } : null,
    g && t(g.scope) ? { label: 'Scope', value: t(g.scope), mono: false } : null,
    g && t(g.algorithm) ? { label: 'Algorithm', value: t(g.algorithm), mono: false } : null,
  ].filter((p): p is { label: string; value: string; mono: boolean } => p !== null);
  const notes = g ? t(g.notes) : '';
  if (parts.length === 0 && !notes) return null;
  return (
    <Card className="pad endpoint-rate-limit" role="region" aria-label="Rate limit">
      <h2 className="h2-sm">Rate limit</h2>
      <dl className="rl-kv">
        {parts.map((p) => (
          <div key={p.label}>
            <dt className="faint small">{p.label}</dt>
            <dd className={p.mono ? 'mono' : undefined}>{p.value}</dd>
          </div>
        ))}
      </dl>
      {notes ? <p className="small muted">{notes}</p> : null}
    </Card>
  );
}
