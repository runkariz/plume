import type { ChangeClass, ChangeItem, ChangeValue, ReleaseReview } from '@/api/types';

/** The review of a build, in words (nothing is held after a publish: the maintainer keeps it or rolls it back). */
export const REVIEW_LABEL: Record<ReleaseReview, string> = {
  pending: 'Pending review',
  kept: 'Kept',
  rolled_back: 'Rolled back',
};

/** Where a change comes from. Suspect and unknown are the extractor's, not the vendor's. */
export const CLASS_LABEL: Record<ChangeClass, string> = {
  confirmed: 'Confirmed in the docs',
  likely: 'Likely (vendor changelog)',
  suspect: 'Suspect: extraction artifact',
  unknown: 'No source evidence',
};

export const OP_LABEL: Record<string, string> = {
  added: 'added',
  removed: 'removed',
  type: 'type changed',
  required: 'required changed',
  description: 'description changed',
  enum: 'enum changed',
  renamed: 'renamed',
};

/** Only an http(s) address is a link: a source URL is data from a package. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}

/** What the change is about: "GET /orders.json", "Order model", or the document id. */
export function subjectText(i: ChangeItem): string {
  const s = i.subject;
  if (s.method && s.path) return `${s.method} ${s.path}`;
  if (s.model) return `${s.model} model`;
  return s.docId ?? i.kind;
}

/** "string, optional": the values of one side of a change (the quote is shown on its own). */
export function valueText(v: ChangeValue | null | undefined): string {
  if (!v) return 'none';
  const parts = [
    v.type ?? null,
    v.required === true ? 'required' : v.required === false ? 'optional' : null,
  ].filter((x): x is string => Boolean(x));
  return parts.length ? parts.join(', ') : v.quote ? 'described' : 'none';
}

export const DECISION_LABEL: Record<string, string> = {
  keep: 'Kept',
  rollback: 'Rolled back',
  rollforward: 'Rolled forward',
  promote: 'Promoted to confirmed',
  demote: 'Demoted',
};
