import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import type { HttpMethod } from '@/api/types';
import { breakable } from '@/lib/breakable';
import { docHref, endpointOfId } from '@/lib/docHref';
import { MethodBadge } from './Method';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

/** A link to one endpoint document, labelled with the method and path its id carries (else the id). */
export function EndpointLink({ api, id }: { api: string; id: string }) {
  const e = endpointOfId(id);
  return (
    <Link to={docHref(api, id)} className="linked-endpoint" title={id}>
      {e && METHODS.includes(e.method) ? <MethodBadge method={e.method as HttpMethod} /> : null}{' '}
      <span className="mono">{breakable(e ? e.path : id)}</span>
      {e?.operation ? <span className="faint small mono"> · {e.operation}</span> : null}
    </Link>
  );
}

/**
 * The endpoints a guide is about, or the endpoints that need a scope: links, the first `collapseAt` shown and the
 * rest behind a button. Nothing when the list is empty or absent.
 */
export function EndpointLinks({
  api,
  ids,
  label,
  collapseAt = 6,
}: {
  api: string;
  ids: string[] | undefined;
  label: string;
  collapseAt?: number;
}) {
  const [all, setAll] = useState(false);
  if (!ids || ids.length === 0) return null;
  const shown = all ? ids : ids.slice(0, collapseAt);
  return (
    <div>
      <ul className="linked-list" aria-label={label}>
        {shown.map((id) => (
          <li key={id}>
            <EndpointLink api={api} id={id} />
          </li>
        ))}
      </ul>
      {ids.length > collapseAt ? (
        <div className="show-all">
          <button type="button" className="linkbtn" onClick={() => setAll((v) => !v)}>
            {all ? `Show the first ${collapseAt}` : `Show all ${ids.length}`}
          </button>
        </div>
      ) : null}
    </div>
  );
}

const TITLES_AT_MOST = 12;

/** The titles of up to a dozen documents, fetched one by one; a title that does not arrive stays the id. */
function useTitles(api: string, ids: string[]): Record<string, string> {
  const client = useApiClient();
  const [titles, setTitles] = useState<Record<string, string>>({});
  const key = ids.slice(0, TITLES_AT_MOST).join('\n');
  useEffect(() => {
    const ctl = new AbortController();
    for (const id of key ? key.split('\n') : []) {
      client
        .getDocument(api, id, ctl.signal)
        .then((d) => {
          if (d.title) setTitles((t) => ({ ...t, [id]: d.title }));
        })
        .catch(() => undefined);
    }
    return () => ctl.abort();
  }, [client, api, key]);
  return titles;
}

/** The knowledge units (guides) that name an endpoint: links titled with the guide's own title. */
export function GuideLinks({ api, ids }: { api: string; ids: string[] | undefined }) {
  const list = ids ?? [];
  const titles = useTitles(api, list);
  if (list.length === 0) return null;
  return (
    <ul className="linked-list" aria-label="Related guides">
      {list.map((id) => (
        <li key={id}>
          <Link to={docHref(api, id)} title={id}>
            {titles[id] ?? id}
          </Link>
        </li>
      ))}
    </ul>
  );
}
