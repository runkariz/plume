import { apiBaseUrl } from '@/api/config';

/**
 * The URL of an API's own icon, served by Plume (`logo.url` is a path like "/v1/apis/shopify/icon").
 * Anything else (an absolute or external URL, a data: URL, a path outside /v1/) is refused: the web never loads
 * third-party images. Returns null when there is nothing safe to show (use the letter tile then).
 */
export function iconSrc(url: string | null | undefined, base?: string): string | null {
  if (!url || !url.startsWith('/v1/') || url.startsWith('//') || url.includes('..')) return null;
  try {
    return `${base ?? apiBaseUrl()}${url}`;
  } catch {
    return null; // no API base configured
  }
}
