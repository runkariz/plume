import { useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { ModelImpact } from '@/api/types';
import { Chip } from '@/components';
import { apiLabel } from '@/lib/names';
import { changeText, vendorHref } from './ChangeBrief';

/**
 * The rows behind "N mappings affected": the fields a visible change touches, each linked to the mapping (a model
 * page) with what changed in plain text, BREAKING as text, and the vendor's page. `kind` picks the model's or the set's
 * route. Says so when the list cannot be loaded; nothing when there are no rows.
 */
export function AffectedRows({ id, kind }: { id: string; kind: 'model' | 'set' }) {
  const client = useApiClient();
  const [params] = useSearchParams();
  const load = useCallback(
    (signal: AbortSignal): Promise<ModelImpact> =>
      kind === 'model' ? client.getModelImpact(id, signal) : client.getSetImpact(id, signal),
    [client, id, kind],
  );
  const { state } = useAsync(load);
  if (state.status === 'loading')
    return <p className="faint small">Loading the affected mappings…</p>;
  if (state.status === 'error')
    return <p className="faint small">The list of affected mappings could not be loaded.</p>;
  if (state.data.affected.length === 0) return null;
  return (
    <ul className="plain impact-rows" aria-label="Affected mappings">
      {state.data.affected.map((a) => {
        const next = new URLSearchParams(params);
        next.set('field', a.field);
        next.set('api', a.api);
        const vendor = vendorHref(a.change);
        return (
          <li key={`${a.member ?? ''}/${a.api}/${a.field}/${a.change.id}`}>
            {a.member ? <b>{a.member}: </b> : null}
            {kind === 'model' ? (
              <Link to={`?${next.toString()}`} className="mono">
                {a.field}
              </Link>
            ) : (
              <span className="mono">{a.field}</span>
            )}{' '}
            <span className="faint small">{apiLabel({ id: a.api })}</span>{' '}
            {a.change.breaking ? (
              <Chip tone="bad">
                <span aria-hidden="true">⚠ </span>Breaking
              </Chip>
            ) : null}
            <div className="small">
              {changeText(a.change)}
              {a.change.perVendorChangelog || a.change.class === 'likely' ? (
                <span className="muted"> · per the vendor&apos;s changelog</span>
              ) : null}
              {vendor ? (
                <>
                  {' · '}
                  <a href={vendor} target="_blank" rel="noreferrer noopener">
                    Vendor page
                  </a>
                </>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
