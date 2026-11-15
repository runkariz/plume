/** The page of a document of an API in the web app. */
export const docHref = (api: string, docId: string) =>
  `/apis/${encodeURIComponent(api)}/documents/${encodeURIComponent(docId)}`;
