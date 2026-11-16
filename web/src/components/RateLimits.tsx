import type { ApiRateLimit, EndpointRateLimit, RateLimitGroup } from '@/api/types';
import { Card } from './Card';
import { Chip } from './Chip';

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

/** How an API limits calls: one row per entry of the package's rateLimits. Nothing is shown when it has none. */
export function RateLimitsCard({ limits }: { limits: ApiRateLimit[] | undefined }) {
  if (!limits || limits.length === 0) return null;
  return (
    <Card className="pad rate-limits" role="region" aria-label="Rate limits">
      <h2 style={{ marginBottom: 12 }}>Rate limits</h2>
      <ul className="rl-list">
        {limits.map((l, i) => {
          const numbers = amount(l);
          const hs = headers(l.headerNames);
          return (
            <li key={`${t(l.scope)}-${t(l.group)}-${i}`}>
              <div className="row" style={{ gap: 6 }}>
                {t(l.scope) ? <Chip>{t(l.scope)}</Chip> : null}
                {t(l.group) ? <span className="mono">{t(l.group)}</span> : null}
                {numbers ? <b>{numbers}</b> : null}
                {t(l.algorithm) ? <Chip tone="info">{t(l.algorithm)}</Chip> : null}
              </div>
              {hs.length > 0 ? (
                <p className="small muted">
                  Reported in{' '}
                  {hs.map((h, j) => (
                    <span key={h}>
                      {j > 0 ? ', ' : ''}
                      <span className="mono">{h}</span>
                    </span>
                  ))}
                </p>
              ) : null}
              {t(l.notes) ? <p className="small muted">{t(l.notes)}</p> : null}
            </li>
          );
        })}
      </ul>
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
