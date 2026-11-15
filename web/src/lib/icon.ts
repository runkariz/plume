/**
 * The URL of an API's own icon, served by Plume (`logo.url` is a path like "/v1/apis/shopify/icon") on the API
 * base the caller passes (from the API client in use). Anything else (an absolute or external URL, a data: URL, a
 * path outside /v1/) is refused: the web never loads third-party images. Returns null when there is nothing safe
 * to show, or no API base to load it from (use the letter tile then). It reads no configuration itself, so the
 * embedded view (which has no API) does not carry the app's environment.
 */
export function iconSrc(url: string | null | undefined, base?: string | null): string | null {
  if (!base) return null;
  if (!url || !url.startsWith('/v1/') || url.startsWith('//') || url.includes('..')) return null;
  return `${base}${url}`;
}
