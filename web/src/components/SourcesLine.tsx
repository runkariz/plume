import type { ApiSource } from '@/api/types';
import { formatDate } from '@/lib/format';

const KIND_LABEL: Record<string, string> = {
  docs: 'Docs',
  spec: 'OpenAPI spec',
  changelog: 'Changelog',
  sdk: 'SDK',
  other: 'Other',
};

/** Only an http(s) address is a link: a source url comes from a package, whatever the server filtered. */
function href(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}

function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * Where the docs of this build came from and when they were extracted: "Sources: Docs · OpenAPI spec · Changelog"
 * (each linked, in a new tab) and "Extracted on 14 Nov 2026 from docs, OpenAPI spec". Renders nothing for a build
 * without these fields (older builds: `sources` is null, `extractedAt` null), and shows only what exists.
 */
export function SourcesLine({
  sources,
  extractedAt,
}: {
  sources?: ApiSource[] | null;
  extractedAt?: string | null;
}) {
  const list = (sources ?? []).filter((s) => href(s.url) !== null);
  if (list.length === 0 && !extractedAt) return null;
  const label = (s: ApiSource) => KIND_LABEL[s.kind] ?? 'Other';
  // two sources of one kind are told apart by their host
  const count = new Map<string, number>();
  for (const s of list) count.set(label(s), (count.get(label(s)) ?? 0) + 1);
  const text = (s: ApiSource) =>
    (count.get(label(s)) ?? 0) > 1 ? `${label(s)} (${host(s.url)})` : label(s);
  const kinds = [...new Set(list.map((s) => label(s)))];
  return (
    <p className="muted small sources-line" data-testid="sources-line">
      {list.length > 0 ? (
        <>
          <span>Sources: </span>
          {list.map((s, i) => (
            <span key={s.url}>
              {i > 0 ? ' · ' : ''}
              <a
                href={href(s.url) ?? undefined}
                target="_blank"
                rel="noreferrer noopener"
                title={s.fetchedAt ? `Fetched ${formatDate(s.fetchedAt)}` : undefined}
              >
                {text(s)}
              </a>
            </span>
          ))}
        </>
      ) : null}
      {extractedAt ? (
        <>
          {list.length > 0 ? ' · ' : ''}
          Extracted on {formatDate(extractedAt)}
          {kinds.length > 0
            ? ` from ${kinds.map((k) => k.toLowerCase().replace('openapi spec', 'OpenAPI spec')).join(', ')}`
            : ''}
        </>
      ) : null}
    </p>
  );
}
