import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip } from '@/components';
import { formatDate, shortBuild } from '@/lib/format';

/**
 * The mappings maintainers verified from users' reports for this model's concept, as the maintainer sees them: each is
 * "verified (user report #id)", linked to the report. It is not a claim about this stored model, whose source for a field
 * may differ. Nothing for a reader, when there are none, or when the server cannot say.
 */
export function VerifiedMappings({ concept }: { concept: string | undefined }) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) =>
      concept ? client.listVerifiedMappings({ concept }, signal) : Promise.resolve([]),
    [client, concept],
  );
  const { state } = useAsync(load);
  if (state.status !== 'ready' || state.data.length === 0) return null;
  return (
    <Card className="pad" role="region" aria-label="Verified mappings">
      <h2 className="h2-sm">
        Verified mappings <span className="faint small">({state.data.length})</span>
      </h2>
      <p className="faint small">
        Accepted from users&apos; reports and shown first in sessions. The mappings of this stored
        model may differ.
      </p>
      <ul className="plain verified-list" aria-label="Verified mappings of this concept">
        {state.data.map((m) => (
          <li key={m.id} className="verified-row">
            <div className="row" style={{ gap: 8 }}>
              <span className="mono">{m.canonicalField}</span>
              <span className="faint small">← {m.api}</span>
              <Chip tone={m.suspended ? 'warn' : 'ok'}>{m.suspended ? 'suspended' : 'active'}</Chip>
            </div>
            {m.notAvailable ? (
              <div className="small">
                <b>not available on {m.api}</b>
                {m.notFrom?.length ? (
                  <>
                    {' '}
                    · not <span className="mono">{m.notFrom.join(', ')}</span>
                  </>
                ) : null}
              </div>
            ) : (
              <div className="mono small">{m.paths.join(', ')}</div>
            )}
            <div className="faint small">
              <Link to={`/maintainer/mapping-reports/${encodeURIComponent(m.reportId)}`}>
                verified (user report {m.reportId})
              </Link>
              {m.build ? <> · validated on build {shortBuild(m.build)}</> : null}
              {m.validatedAt ? <> · {formatDate(m.validatedAt)}</> : null}
              {m.suspended && m.suspendedReason ? <> · {m.suspendedReason}</> : null}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
