import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import type { MappingEvidence } from '@/api/types';
import { docHref } from '@/lib/docHref';

/** How much of the document is shown on each side of the quote. */
const CONTEXT = 160;

/**
 * Where the quote stands in the document: the text around its first occurrence, with the quote marked. Null when the
 * quote is not in the text (then the quote is shown alone).
 */
export function excerptAround(
  text: string,
  quote: string,
): { before: string; match: string; after: string; cutBefore: boolean; cutAfter: boolean } | null {
  if (!quote.trim()) return null;
  const at = text.indexOf(quote);
  if (at < 0) return null;
  const start = Math.max(0, at - CONTEXT);
  const end = Math.min(text.length, at + quote.length + CONTEXT);
  return {
    before: text.slice(start, at),
    match: quote,
    after: text.slice(at + quote.length, end),
    cutBefore: start > 0,
    cutAfter: end < text.length,
  };
}

/**
 * One citation of a suggested mapping: the cited document (a link) and its quote marked in the document's own text, read
 * from the reader API. A citation without a quote says why. The quote is shown on its own when the document cannot be read.
 */
export function Citation({ api, e }: { api: string; e: MappingEvidence }) {
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getDocument(api, e.docId, signal),
    [client, api, e.docId],
  );
  const { state } = useAsync(load);
  const quote = e.quote?.trim() ?? '';
  const excerpt = state.status === 'ready' && quote ? excerptAround(state.data.text, quote) : null;
  return (
    <figure className="map-citation">
      <figcaption className="small">
        <Link to={docHref(api, e.docId)} className="mono">
          {e.docId}
        </Link>
        {state.status === 'ready' && state.data.title ? (
          <span className="faint"> · {state.data.title}</span>
        ) : null}
      </figcaption>
      {quote ? (
        excerpt ? (
          <blockquote className="map-quote">
            {excerpt.cutBefore ? '… ' : ''}
            {excerpt.before}
            <mark>{excerpt.match}</mark>
            {excerpt.after}
            {excerpt.cutAfter ? ' …' : ''}
          </blockquote>
        ) : (
          <blockquote className="map-quote">
            <mark>{quote}</mark>
            {state.status === 'ready' ? (
              <span className="faint small"> (not found in the document text as it is now)</span>
            ) : null}
          </blockquote>
        )
      ) : (
        <p className="faint small">cited without quote{e.noQuote ? `: ${e.noQuote}` : ''}</p>
      )}
    </figure>
  );
}
