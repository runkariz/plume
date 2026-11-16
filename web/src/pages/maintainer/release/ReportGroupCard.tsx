import { useState } from 'react';
import { useApiClient } from '@/api/context';
import type { ChangeItem, ReportGroup } from '@/api/types';
import { Card, Chip } from '@/components';
import { PagedChanges } from './PagedChanges';

/**
 * One rule of the extraction report: the server's title and one-sentence explanation, and its changes. The notes carry
 * only the first 50 of a group; the rest comes from GET .../report/{rule} when the maintainer asks for it (or loads
 * all of them to search through).
 */
export function ReportGroupCard({
  api,
  build,
  group,
  query,
  onChanged,
}: {
  api: string;
  build: string;
  group: ReportGroup;
  query: string;
  onChanged: () => void;
}) {
  const client = useApiClient();
  const total = group.count ?? group.items.length;
  const [extra, setExtra] = useState<ChangeItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const items = [...group.items, ...extra];

  /** Loads from the server what is not loaded yet: `limit` more, or everything (pages of 200). */
  async function load(limit: number | 'all') {
    setError(null);
    try {
      const got: ChangeItem[] = [];
      let cursor: number | null = group.items.length + extra.length;
      while (cursor !== null) {
        const page = await client.getReportPage(
          api,
          build,
          group.rule,
          cursor,
          limit === 'all' ? 200 : limit,
        );
        got.push(...page.items);
        cursor = limit === 'all' ? page.nextCursor : null;
      }
      setExtra((e) => [...e, ...got]);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'Could not load more of this group.');
    }
  }

  return (
    <Card className="pad" role="region" aria-label={group.title}>
      <h3 className="h3-sm">
        {group.title} <span className="faint small mono">{group.rule}</span> <Chip>{total}</Chip>
      </h3>
      <p className="muted small">{group.explanation}</p>
      <PagedChanges
        api={api}
        build={build}
        items={items}
        total={total}
        query={query}
        onChanged={onChanged}
        label={`${group.title}: changes`}
        loadMore={(n) => load(n)}
        loadAll={() => load('all')}
      />
      {error ? (
        <p role="alert" className="form-error small">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
