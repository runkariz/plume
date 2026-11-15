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
