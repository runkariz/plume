import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip, Crumbs, EmptyState, ErrorState, LoadingState } from '@/components';
import { formatDate, shortBuild } from '@/lib/format';
import { REVIEW_LABEL } from './notes';

const TONE = { pending: 'warn', kept: 'ok', rolled_back: 'bad' } as const;

/** The builds of an API that have release notes, newest first, with each one's review (maintainer). */
export function BuildsPage() {
  const { apiId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.listReleaseNotes(apiId, signal),
    [client, apiId],
  );
  const { state, retry } = useAsync(load);
  const crumbs = [
    { label: 'Maintainer', to: '/maintainer' },
    { label: apiId },
    { label: 'Builds' },
  ];
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <h1 className="h1-sm">Builds of {apiId}</h1>
      </div>
      {state.status === 'loading' ? <LoadingState label="Loading the builds" /> : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not load the builds"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {state.status === 'ready' && state.data.length === 0 ? (
        <EmptyState title="No builds with release notes">
          Release notes appear after a build is loaded against an earlier one: the first build of an
          API has none.
        </EmptyState>
      ) : null}
      {state.status === 'ready' && state.data.length > 0 ? (
        <Card className="pad">
          <ul className="plain build-list" aria-label="Builds">
            {state.data.map((b) => (
              <li key={b.to} className="build-row">
                <div className="build-main">
                  <Link className="mono" to={`/maintainer/apis/${apiId}/builds/${b.to}/notes`}>
                    {shortBuild(b.to)}
                  </Link>{' '}
                  <span className="faint small">
                    docs as of {b.toDocsAsOf ? formatDate(b.toDocsAsOf) : 'unknown'} · compared with{' '}
                    {shortBuild(b.from)}
                  </span>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {b.tagged ? <Chip tone="acc">latest</Chip> : null}
                  <Chip tone={TONE[b.review]}>{REVIEW_LABEL[b.review]}</Chip>
                  {b.needsAttention ? <Chip tone="warn">Needs attention</Chip> : null}
                  <span className="small muted">
                    {b.counts.confirmed + b.counts.likely} visible
                    {b.counts.breaking ? `, ${b.counts.breaking} breaking` : ''}
                    {b.counts.suspect ? ` · ${b.counts.suspect} suspect` : ''}
                    {b.counts.unknown ? ` · ${b.counts.unknown} unknown` : ''}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}

/**
 * A link to an API's release review, only when the API has notes (feature detection: a server without them answers
 * an error or nothing, and this renders nothing). The link goes to the latest build's notes; a pending build that needs
 * attention is flagged.
 */
export function ReleaseReviewLink({
  api,
  label = 'Release review',
}: {
  api: string;
  label?: string;
}) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.listReleaseNotes(api, signal),
    [client, api],
  );
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.length === 0) return null;
  const latest = state.data.find((b) => b.tagged) ?? state.data[0];
  const attention = state.data.some((b) => b.review === 'pending' && b.needsAttention);
  return (
    <span className="release-link">
      <Link className="btn" to={`/maintainer/apis/${api}/builds/${latest?.to ?? ''}/notes`}>
        {label}
      </Link>
      {attention ? <Chip tone="warn">Needs attention</Chip> : null}
    </span>
  );
}
