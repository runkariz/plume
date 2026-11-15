import { Link } from 'react-router-dom';
import { MethodBadge } from '@/components';
import type { EndpointRefs, HttpMethod } from '@/api/types';
import { docHref } from '@/pages/models/MappingTable';
import { breakable } from '@/lib/breakable';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

/**
 * An endpoint the package mentions by its stream id (e.g. "post-admin-api-latest-webhooks-json-2026-10").
 * Resolved by the API: METHOD + path, linked to the endpoint's page. Not in this build: the raw id, marked.
 * An older server that sends no refs: the raw id only.
 */
export function EndpointRef({
  apiId,
  endpointId,
  refs,
}: {
  apiId: string;
  endpointId: string;
  refs?: EndpointRefs;
}) {
  const ref = refs?.[endpointId];
  if (ref) {
    return (
      <span className="endpoint-ref">
        {METHODS.includes(ref.method) ? <MethodBadge method={ref.method as HttpMethod} /> : null}{' '}
        <Link className="mono" to={docHref(apiId, ref.docId)} title={endpointId}>
          {breakable(ref.path)}
        </Link>
      </span>
    );
  }
  return (
    <span className="endpoint-ref">
      <span className="mono" title={endpointId}>
        {endpointId}
      </span>
      {refs && endpointId in refs ? (
        <span className="faint small"> (not in this build)</span>
      ) : null}
    </span>
  );
}
