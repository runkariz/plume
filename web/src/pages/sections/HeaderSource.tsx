import type { AuthSchemeDetail } from '@/api/types';

type Header = Pick<
  AuthSchemeDetail,
  'headerName' | 'headerPrefix' | 'headerFormat' | 'headerSource' | 'headerEvidence' | 'headerNote'
>;

/**
 * The header as a client sends it: "Authorization: Bearer <token>", with exactly one space between the prefix and the
 * token whether the prefix ends in a space ("Bearer ") or not ("Bearer"). The server's own `headerFormat` when it sends
 * one; else built from the name and the prefix (an older server). Null without a prefix and a format (then the header
 * name alone is shown, as before).
 */
export function headerLine(
  h: Pick<Header, 'headerName' | 'headerPrefix'> & { headerFormat?: string | null },
): string | null {
  const format = h.headerFormat?.trim();
  if (format) return format;
  const prefix = h.headerPrefix?.trim();
  return h.headerName && prefix ? `${h.headerName}: ${prefix} <token>` : null;
}

/**
 * Where the header value comes from. For the OAuth 2.0 standard the label the server sets is shown in the open, next to
 * the header, as a plain note (never a quote: the vendor did not say it); for the vendor's own header its quote is shown
 * as one. A scheme whose source is unknown shows nothing extra.
 */
export function HeaderSource({ scheme }: { scheme: Header }) {
  const note = scheme.headerNote?.trim();
  const quote = scheme.headerSource === 'vendor' ? scheme.headerEvidence?.trim() : null;
  if (!note && !quote) return null;
  return (
    <div className="header-source">
      {note ? <p className="faint small header-note">{note}</p> : null}
      {quote ? (
        <blockquote className="evidence header-evidence">
          <p>“{quote}”</p>
          <cite className="faint small">the vendor&apos;s docs</cite>
        </blockquote>
      ) : null}
    </div>
  );
}
