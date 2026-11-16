/**
 * The operation of an endpoint document whose id carries one: when two operations of a package share METHOD and path
 * (Mirakl's three GET /{file_path} downloads) their ids are "endpoint:GET~/{file_path}@get-or15". The method and
 * path come from the document's own fields, never from the id; the id only says which operation it is. Taken as the
 * rest of the id after "endpoint:METHOD~path" (a path may itself contain "@"), null for any other id.
 */
export function operationOf(
  docId: string | null | undefined,
  method: string | null | undefined,
  path: string | null | undefined,
): string | null {
  if (!docId || !method || !path) return null;
  const head = `endpoint:${method}~${path}`;
  if (!docId.startsWith(head)) return null;
  const rest = docId.slice(head.length);
  return rest.startsWith('@') && rest.length > 1 ? rest.slice(1) : null;
}

/** The page of a document of an API in the web app. */
export const docHref = (api: string, docId: string) =>
  `/apis/${encodeURIComponent(api)}/documents/${encodeURIComponent(docId)}`;

/**
 * The path to show for an endpoint: the one the vendor serves (realPath, e.g. "/vendor/orders/v1/purchaseOrders")
 * when the package says it, else the package's own path. `operationOf` keeps using the package path: the id is built
 * from it.
 */
export function shownPath(x: { path?: string | null; realPath?: string | null }): string | null {
  return x.realPath || x.path || null;
}

const ENDPOINT_ID = /^endpoint:([A-Z]+)~(.+)$/;

/**
 * What an endpoint document id says about itself, for a link label when only the id is known ("endpoint:GET~/orders"
 * or "endpoint:GET~/{file_path}@get-or15"): the method, the path and the operation. Null for any other id; the label
 * is only a reading of the id the server sent, the page it links to shows the document's own fields.
 */
export function endpointOfId(
  docId: string,
): { method: string; path: string; operation: string | null } | null {
  const m = ENDPOINT_ID.exec(docId);
  if (!m) return null;
  const method = m[1] as string;
  const rest = m[2] as string;
  const at = rest.lastIndexOf('@');
  // a path may contain "@"; an operation suffix has no "/" after it
  if (at > 0 && !rest.slice(at + 1).includes('/') && rest.slice(at + 1) !== '')
    return { method, path: rest.slice(0, at), operation: rest.slice(at + 1) };
  return { method, path: rest, operation: null };
}

/** The id of an auth scheme as the scheme page takes it ("auth:oauth2" -> "oauth2"). */
export const schemeIdOf = (authId: string): string =>
  authId.startsWith('auth:') ? authId.slice('auth:'.length) : authId;
