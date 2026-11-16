import type { ApiSource } from '@/api/types';
import { formatDate } from '@/lib/format';

const ORDER = ['docs', 'spec', 'changelog', 'sdk', 'other'] as const;
type Kind = (typeof ORDER)[number];

const ONE: Record<Kind, string> = {
  docs: 'Docs',
  spec: 'OpenAPI spec',
  changelog: 'Changelog',
  sdk: 'SDK',
  other: 'Other',
};
const MANY: Record<Kind, string> = {
  docs: 'docs pages',
  spec: 'OpenAPI specs',
  changelog: 'changelogs',
  sdk: 'SDKs',
  other: 'other sources',
};

/** An unknown kind is "other". */
export const kindOf = (s: ApiSource): Kind =>
  (ORDER as readonly string[]).includes(s.kind) ? (s.kind as Kind) : 'other';

/** Only an http(s) address is a link: a source url comes from a package, whatever the server filtered. */
function parse(url: string): URL | null {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u : null;
  } catch {
    return null;
  }
}

/** The host a source is read from, for secondary text. */
export const hostOf = (url: string): string => parse(url)?.host ?? url;

/**
 * A readable name: a spec is its file name ("vendorOrders.json"), anything else is what it is ("Docs", "Changelog").
 * A file name is read from the last path segment; a url without one falls back to the kind.
 */
export function sourceLabel(s: ApiSource): string {
  const k = kindOf(s);
  if (k === 'spec') {
    const last = parse(s.url)?.pathname.split('/').filter(Boolean).pop();
    if (last) {
      try {
        return decodeURIComponent(last);
      } catch {
        return last;
      }
    }
  }
  return ONE[k];
}

export interface SourceGroup {
  /** The one shown (the host that has a .com, else the first). */
  primary: ApiSource;
  /** The same page on another host (an alias): kept in the detail as "also linked as ...". */
  aliases: ApiSource[];
}

/** Two urls are the same page when only the host differs by an alias: a leading "www." or a missing ".com". */
function pageKey(s: ApiSource): string {
  const u = parse(s.url);
  if (!u) return `${kindOf(s)}|${s.url}`;
  const host = u.hostname
    .toLowerCase()
    .replace(/^www\./, '')
    .replace(/\.com$/, '');
  return `${kindOf(s)}|${host}|${u.pathname.replace(/\/+$/, '')}|${u.search}`;
}

/** The http(s) sources, one per page: host aliases of the same page collapse onto the host with a .com. */
export function collapseSources(sources: ApiSource[] | null | undefined): SourceGroup[] {
  const groups = new Map<string, ApiSource[]>();
  for (const s of sources ?? []) {
    if (!parse(s.url)) continue;
    const k = pageKey(s);
    groups.set(k, [...(groups.get(k) ?? []), s]);
  }
  return [...groups.values()].map((all) => {
    const primary = all.find((s) => hostOf(s.url).toLowerCase().endsWith('.com')) ?? all[0];
    return { primary: primary as ApiSource, aliases: all.filter((s) => s !== primary) };
  });
}

function role(r: string | null | undefined): string | null {
  if (!r) return null;
  if (r.startsWith('discovered')) return 'Discovered';
  return r.charAt(0).toUpperCase() + r.slice(1);
}

/**
 * Where the docs of this build came from, as ONE compact line: "Sources: Docs · 13 OpenAPI specs · Changelog ·
 * Extracted 16 Nov 2026" (a lone source of a kind is a link, several are a count), and a disclosure that lists each
 * source: a readable name, its host, kind, when it was fetched, how it was found, and the alias hosts of the same page.
 * Renders nothing for a build without these fields (older builds), and shows only what exists.
 */
export function SourcesLine({
  sources,
  extractedAt,
}: {
  sources?: ApiSource[] | null;
  extractedAt?: string | null;
}) {
  const groups = collapseSources(sources);
  if (groups.length === 0 && !extractedAt) return null;
  const byKind = ORDER.map((k) => ({
    k,
    items: groups.filter((g) => kindOf(g.primary) === k),
  })).filter((x) => x.items.length > 0);
  const detail = groups.length > 1 || groups.some((g) => g.aliases.length > 0);
  const sorted = byKind.flatMap((x) =>
    [...x.items].sort((a, b) => sourceLabel(a.primary).localeCompare(sourceLabel(b.primary))),
  );
  return (
    <div className="sources" data-testid="sources">
      <p className="muted small sources-line" data-testid="sources-line">
        {byKind.length > 0 ? <span>Sources: </span> : null}
        {byKind.map((x, i) => (
          <span key={x.k}>
            {i > 0 ? ' · ' : ''}
            {x.items.length === 1 ? (
              <a
                href={parse(x.items[0]?.primary.url ?? '')?.toString()}
                target="_blank"
                rel="noreferrer noopener"
              >
                {ONE[x.k]}
              </a>
            ) : (
              `${x.items.length} ${MANY[x.k]}`
            )}
          </span>
        ))}
        {extractedAt ? (
          <>
            {byKind.length > 0 ? ' · ' : ''}
            Extracted {formatDate(extractedAt)}
          </>
        ) : null}
      </p>
      {detail ? (
        <details className="sources-detail small" data-testid="sources-detail">
          <summary>All sources ({groups.length})</summary>
          <ul className="plain sources-list">
            {sorted.map((g) => {
              const s = g.primary;
              const r = role(s.role);
              return (
                <li key={s.url}>
                  <a href={parse(s.url)?.toString()} target="_blank" rel="noreferrer noopener">
                    {sourceLabel(s)}
                  </a>{' '}
                  <span className="faint">{hostOf(s.url)}</span>
                  <span className="muted">
                    {' · '}
                    {ONE[kindOf(s)]}
                    {s.fetchedAt ? ` · fetched ${formatDate(s.fetchedAt)}` : ''}
                    {r ? ` · ${r}` : ''}
                  </span>
                  {g.aliases.length > 0 ? (
                    <span className="faint">
                      {' '}
                      · also linked as {g.aliases.map((a) => hostOf(a.url)).join(', ')}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
