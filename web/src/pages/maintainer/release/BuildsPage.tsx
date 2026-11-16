import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip, Crumbs, EmptyState, ErrorState, LoadingState } from '@/components';
import { formatDate, shortBuild } from '@/lib/format';
import { REVIEW_LABEL } from './notes';

const TONE = { pending: 'warn', kept: 'ok', rolled_back: 'bad' } as const;

/** The builds of an API, newest first, with each build's release review (maintainer). */
export function BuildsPage() {
  const { apiId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.listBuilds(apiId, signal),
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
          Release notes appear after a build is loaded against an earlier one.
        </EmptyState>
      ) : null}
      {state.status === 'ready' && state.data.length > 0 ? (
        <Card className="pad">
          <ul className="plain build-list" aria-label="Builds">
            {state.data.map((b) => (
              <li key={b.id} className="build-row">
                <div className="build-main">
                  {b.review ? (
                    <Link className="mono" to={`/maintainer/apis/${apiId}/builds/${b.id}/notes`}>
                      {shortBuild(b.id)}
                    </Link>
                  ) : (
                    <span className="mono" title="No release notes: nothing to compare it with">
                      {shortBuild(b.id)}
                    </span>
                  )}{' '}
                  <span className="faint small">
                    docs as of {b.docsAsOf ? formatDate(b.docsAsOf) : 'unknown'} · loaded{' '}
                    {formatDate(b.createdAt)}
                  </span>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {b.tag ? <Chip tone="acc">{b.tag}</Chip> : null}
                  {b.review ? (
                    <Chip tone={TONE[b.review]}>{REVIEW_LABEL[b.review]}</Chip>
                  ) : (
                    <Chip>no notes</Chip>
                  )}
                  {b.needsAttention ? <Chip tone="warn">Needs attention</Chip> : null}
                  {b.review ? (
                    <span className="small muted">
                      {b.counts.confirmed + b.counts.likely} visible
                      {b.counts.breaking ? `, ${b.counts.breaking} breaking` : ''}
                      {b.counts.suspect ? ` · ${b.counts.suspect} suspect` : ''}
                      {b.counts.unknown ? ` · ${b.counts.unknown} unknown` : ''}
                    </span>
                  ) : null}
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
 * A link to an API's release review, only when its latest build has notes (feature detection: a server without them
 * answers nothing useful and this renders nothing). A build that needs attention says so.
 */
export function ReleaseReviewLink({
  api,
  label = 'Release review',
}: {
  api: string;
  label?: string;
}) {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listBuilds(api, signal), [client, api]);
  const { state } = useAsync(load);
  if (state.status !== 'ready') return null;
  const latest = state.data.find((b) => b.tag === 'latest' && b.review);
  const attention = state.data.some((b) => b.review === 'pending' && b.needsAttention);
  if (!latest && !state.data.some((b) => b.review)) return null;
  return (
    <span className="release-link">
      <Link
        className="btn"
        to={
          latest
            ? `/maintainer/apis/${api}/builds/${latest.id}/notes`
            : `/maintainer/apis/${api}/builds`
        }
      >
        {label}
      </Link>
      {attention ? <Chip tone="warn">Needs attention</Chip> : null}
    </span>
  );
}
