import type { BuildPackage, ReleaseNotes, SourceConflict } from '@/api/types';
import { Card, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { plain, safeHref, sourceKindLabel } from './notes';

function Link({ url }: { url: string }) {
  const href = safeHref(url);
  return href ? (
    <a href={href} target="_blank" rel="noreferrer noopener" className="mono small">
      {url}
    </a>
  ) : (
    <span className="mono small">{url} (not a link)</span>
  );
}

function Conflict({ c }: { c: SourceConflict }) {
  return (
    <li className="source-conflict">
      <p className="small">
        <b>{c.unit}</b> <span className="mono">{c.field}</span>
      </p>
      <ul className="plain small">
        {/* one page can state two values */}
        {(c.values ?? []).map((v, i) => (
          <li key={`${v.url}/${i}`}>
            <span className="mono">{plain(v.value)}</span> <span className="faint">from</span>{' '}
            <Link url={v.url} />
          </li>
        ))}
      </ul>
      <p className="small muted">
        Stream chose <span className="mono">{plain(c.chosen)}</span>
        {c.reason ? `: ${c.reason}` : '.'}
      </p>
    </li>
  );
}

/** One side of "where it came from" for the new build: the sources, the run, the changelog urls. */
function PackageSources({ pkg }: { pkg: BuildPackage }) {
  const sources = pkg.sources ?? [];
  const changelogs = (pkg.changelogUrls ?? []).filter((u) => safeHref(u));
  return (
    <>
      {pkg.runId ? (
        <p className="small">
          Stream run <span className="mono">{pkg.runId}</span>
        </p>
      ) : null}
      {sources.length > 0 ? (
        <ul className="plain stack source-list" aria-label="Sources of this build">
          {sources.map((s) => (
            <li key={s.url}>
              <Chip>{sourceKindLabel(s.kind)}</Chip> <Link url={s.url} />
              <span className="faint small">
                {s.fetchedAt ? ` · fetched ${formatDate(s.fetchedAt)}` : ''}
                {s.version ? ` · version ${s.version}` : ''}
                {s.role ? ` · ${s.role}` : ''}
              </span>
              {s.fallback ? (
                <>
                  {' '}
                  <Chip tone="warn">only the manifest&apos;s source url</Chip>
                </>
              ) : null}
              {s.contentSha256 ? (
                <span className="mono faint small"> {s.contentSha256.slice(0, 19)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="small muted">Sources: not recorded for this build.</p>
      )}
      {changelogs.length > 0 ? (
        <p className="small">
          Changelog:{' '}
          {changelogs.map((u, i) => (
            <span key={u}>
              {i > 0 ? ', ' : ''}
              <Link url={u} />
            </span>
          ))}
        </p>
      ) : null}
    </>
  );
}

/**
 * The maintainer's view of where a build came from, all of it only when the server sent it: the full source list with
 * stream's run id, and the source conflicts stream reported. "Not compared" is NEVER shown as "no conflicts".
 */
export function SourcesPanel({ n }: { n: ReleaseNotes }) {
  const pkg = n.package?.to;
  const check = n.conflictCheck;
  const conflicts = n.conflicts ?? [];
  const hasSources = pkg && (pkg.sources || pkg.runId || pkg.changelogUrls);
  if (!hasSources && !check && conflicts.length === 0) return null;
  const unchecked = check?.notCompared ?? 0;
  return (
    <Card className="pad" role="region" aria-label="Sources and conflicts">
      <h2 className="h2-sm">Sources and conflicts</h2>
      {pkg ? <PackageSources pkg={pkg} /> : null}
      {check && check.checked === 0 && unchecked === 0 ? (
        <p className="small muted" data-testid="conflict-check">
          Stream did not compare sources for this build: no conflict check was recorded.
        </p>
      ) : check ? (
        <p className="small" data-testid="conflict-check">
          Stream compared <b>{check.checked}</b> unit{check.checked === 1 ? '' : 's'} across sources
          {conflicts.length === 0 && check.checked > 0 && unchecked === 0
            ? ' and found no conflicts.'
            : conflicts.length > 0
              ? ` and reported ${conflicts.length} conflict${conflicts.length === 1 ? '' : 's'}.`
              : '.'}
          {unchecked > 0 ? (
            <>
              {' '}
              <Chip tone="warn">
                {unchecked} unit{unchecked === 1 ? '' : 's'} not compared
              </Chip>{' '}
              <span className="muted">
                Stream did not compare these, so this is not the same as “no conflicts”.
              </span>
            </>
          ) : null}
        </p>
      ) : null}
      {conflicts.length > 0 ? (
        <ul className="plain stack" aria-label="Source conflicts">
          {/* stream can report one unit and field more than once: the index keeps the rows apart */}
          {conflicts.map((c, i) => (
            <Conflict key={`${c.unit}/${c.field}/${i}`} c={c} />
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
