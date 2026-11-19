import type { ReactNode } from 'react';
import type { Evidence, ModelOperation, ModelSnapshot, OperationSource } from '@/api/types';
import { Card, Chip } from '@/components';

/** The kinds a model's operations come in; one the server adds later is shown as written. */
const KIND_LABEL: Record<string, string> = {
  read: 'read',
  create: 'create',
  update: 'update',
  set: 'set',
  adjust: 'adjust',
  delete: 'delete',
  other: 'other',
};

export const operationKindLabel = (kind: string) => KIND_LABEL[kind] ?? kind;

/** "POST /admin/api/{version}/x.json" -> the endpoint document id ("endpoint:POST~/admin/api/{version}/x.json"). */
export function endpointDocId(endpoint: string): string | null {
  const m = /^\s*([A-Za-z]+)\s+(\S.*?)\s*$/.exec(endpoint);
  return m && m[1] && m[2] ? `endpoint:${m[1].toUpperCase()}~${m[2]}` : null;
}

/**
 * The document that names the endpoint: a cited document whose id is the endpoint's (or the endpoint's with its
 * operation suffix, "endpoint:GET~/{file_path}@get-or15"), else the id built from the endpoint line.
 */
export function endpointTarget(src: OperationSource): string | null {
  const built = endpointDocId(src.endpoint);
  if (!built) return null;
  const cited = (src.evidence ?? []).find(
    (e) => e.docId && (e.docId === built || e.docId.startsWith(`${built}@`)),
  );
  return cited?.docId ?? built;
}

/** A cited quote, or the reason there is none ("cited without quote: ..."). */
export function EvidenceLine({ e }: { e: Evidence }) {
  if (e.noQuote && !e.quote) return <span className="faint">cited without quote: {e.noQuote}</span>;
  return <q>{e.quote}</q>;
}

function Cell({
  apiId,
  src,
  endpointLink,
}: {
  apiId: string;
  src: OperationSource | undefined;
  endpointLink?: (apiId: string, docId: string, label: string) => ReactNode;
}) {
  if (!src) return <span className="faint small">No equivalent</span>;
  const target = endpointTarget(src);
  const evidence = src.evidence ?? [];
  return (
    <>
      <div className="mono mtable-path op-endpoint">
        {target && endpointLink ? endpointLink(apiId, target, src.endpoint) : src.endpoint}
      </div>
      {src.fields?.length ? (
        <div className="op-fields" aria-label="Fields">
          {src.fields.map((f) => (
            <code key={f} className="mono small">
              {f}
            </code>
          ))}
        </div>
      ) : null}
      {src.semantics ? <div className="small op-semantics">{src.semantics}</div> : null}
      {evidence.length ? (
        <details className="mtable-cites">
          <summary>
            {evidence.length} citation{evidence.length === 1 ? '' : 's'}
          </summary>
          <ul>
            {evidence.map((e, i) => (
              <li key={`${e.docId ?? ''}-${i}`}>
                <EvidenceLine e={e} />
                {e.docId ? <span className="faint small mono"> {e.docId}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

/** The operations of a model that states some, with the APIs the model pins; empty for a model that states none. */
export function modelOperations(snap: Pick<ModelSnapshot, 'operations'>): ModelOperation[] {
  return (snap.operations ?? []).filter(
    (o) => o && typeof o.name === 'string' && o.sources && typeof o.sources === 'object',
  );
}

type EndpointLink = (apiId: string, docId: string, label: string) => ReactNode;

/** One row per operation, one column per API: the endpoint, the fields it uses and what it means. */
export function OperationsTable({
  snap,
  endpointLink,
}: {
  snap: Pick<ModelSnapshot, 'name' | 'inputs' | 'operations'>;
  /** How an endpoint is shown: a link in the web app; plain text without it (the embedded view has no pages). */
  endpointLink?: EndpointLink;
}) {
  const ops = modelOperations(snap);
  return (
    <table className="mtable-grid op-grid">
      <caption className="sr-only">
        What a client can do with the {snap.name} concept, per API
      </caption>
      <thead>
        <tr>
          <th scope="col">Operation</th>
          {snap.inputs.map((a) => (
            <th scope="col" key={a.id}>
              {a.shortName}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ops.map((o, i) => (
          <tr key={`${o.name}-${i}`}>
            <th scope="row" className="mtable-field">
              <span className="mtable-name">{o.name}</span>
              <span>
                <Chip>{operationKindLabel(o.kind)}</Chip>
              </span>
            </th>
            {snap.inputs.map((a) => (
              <td key={a.id} data-label={a.shortName}>
                <Cell apiId={a.id} src={o.sources[a.id]} endpointLink={endpointLink} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * What a client does with the concept (read, set, adjust ...), on the model page. Nothing when the model states no
 * operations (every model before the server sent them).
 */
export function Operations({
  snap,
  endpointLink,
}: {
  snap: Pick<ModelSnapshot, 'name' | 'inputs' | 'operations'>;
  endpointLink?: EndpointLink;
}) {
  const n = modelOperations(snap).length;
  if (n === 0) return null;
  return (
    <Card className="pad operations" role="region" aria-label="Operations">
      <h2 className="h2-sm">
        Operations <span className="faint small">({n})</span>
      </h2>
      <OperationsTable snap={snap} endpointLink={endpointLink} />
    </Card>
  );
}
