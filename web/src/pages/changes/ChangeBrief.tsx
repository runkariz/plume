import { Link } from 'react-router-dom';
import type { PublicChange } from '@/api/types';
import { Chip } from '@/components';
import { docHref } from '@/lib/docHref';
import { OP_LABEL, safeHref, valueText } from '../maintainer/release/notes';

/** What the change is about: "GET /orders.json", "Order model", or the document id. */
export function subjectOf(i: PublicChange): string {
  const s = i.subject;
  if (s.method && s.path) return `${s.method} ${s.path}`;
  if (s.model) return `${s.model} model`;
  return s.docId ?? i.kind;
}

/** The vendor page of a change, with its anchor when it has one; null unless it is an http(s) address. */
export function vendorHref(item: PublicChange): string | null {
  const href = safeHref(item.vendorUrl);
  if (!href) return null;
  const anchor = (item.anchor ?? '').replace(/^#/, '');
  if (!anchor) return href;
  const u = new URL(href);
  return u.hash ? href : `${href}#${encodeURIComponent(anchor)}`;
}

/** What changed, in one line of plain text: "removed GET /orders.json · fulfillment_status". */
export function changeText(item: PublicChange): string {
  const where = item.subject.fieldPath
    ? `${subjectOf(item)} · ${item.subject.fieldPath}`
    : subjectOf(item);
  return `${OP_LABEL[item.op] ?? item.op} ${where}`;
}

/**
 * One change as users see it: op, BREAKING (text, not colour alone), the subject, before → after, the quote of the
 * docs as plain text, "per the vendor's changelog" on a likely one, and the links (the vendor's page; the document in
 * Plume unless it was removed). Everything from the package is rendered as text.
 */
export function ChangeBrief({
  api,
  item,
  highlighted = false,
}: {
  api: string;
  item: PublicChange;
  highlighted?: boolean;
}) {
  const vendor = vendorHref(item);
  const inPlume =
    item.op !== 'removed' && !item.removedDocument && item.subject.docId
      ? docHref(api, item.subject.docId)
      : null;
  return (
    <li id={`change-${item.id}`} className={`change-brief${highlighted ? ' change-hit' : ''}`}>
      <div className="row" style={{ gap: 6 }}>
        <Chip>{OP_LABEL[item.op] ?? item.op}</Chip>
        {item.breaking ? (
          <Chip tone="bad">
            <span aria-hidden="true">⚠ </span>Breaking
          </Chip>
        ) : null}
        <span className="mono small change-subject">
          {item.subject.fieldPath
            ? `${subjectOf(item)} · ${item.subject.fieldPath}`
            : subjectOf(item)}
        </span>
      </div>
      {item.op !== 'description' || item.before || item.after ? (
        <p className="small">
          <span className="mono">{valueText(item.before)}</span> →{' '}
          <span className="mono">{valueText(item.after)}</span>
          {item.breaking && item.breakingReason ? (
            <span className="muted"> · {item.breakingReason}</span>
          ) : null}
        </p>
      ) : null}
      {item.quote ? <blockquote className="quote">{item.quote}</blockquote> : null}
      <p className="small muted">
        {item.perVendorChangelog || item.class === 'likely' ? (
          <>Per the vendor&apos;s changelog · </>
        ) : null}
        {vendor ? (
          <a href={vendor} target="_blank" rel="noreferrer noopener">
            Vendor page
          </a>
        ) : (
          'No vendor page'
        )}
        {inPlume ? (
          <>
            {' · '}
            <Link to={inPlume}>Open in Plume</Link>
          </>
        ) : null}
      </p>
    </li>
  );
}
