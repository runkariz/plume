import { useState, type FormEvent } from 'react';
import { useApiClient } from '@/api/context';
import { ApiError, type ChangeItem } from '@/api/types';
import { Button, Chip } from '@/components';
import { formatDate } from '@/lib/format';
import { CLASS_LABEL, OP_LABEL, safeHref, subjectText, valueText } from './notes';

const TONE = { confirmed: 'ok', likely: 'info', suspect: 'bad', unknown: 'neutral' } as const;

/**
 * One change of a build for the maintainer: where it comes from (the docs or the extractor), what changed with the
 * quotes of both builds as plain text, the vendor page, the page hashes, and the rules that flagged it. A suspect or
 * unknown change can be promoted to confirmed with a quote the SERVER verifies against this build's source text; a
 * promotion can be undone. All text is the package's: only ever a text node, and a link only for an http(s) address.
 */
export function ChangeRow({
  api,
  build,
  item,
  onChanged,
}: {
  api: string;
  build: string;
  item: ChangeItem;
  onChanged: () => void;
}) {
  const client = useApiClient();
  const [open, setOpen] = useState(false);
  const [quote, setQuote] = useState('');
  const [busy, setBusy] = useState<'promote' | 'demote' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const href = safeHref(item.evidence?.sourceUrl);
  const hashes = item.evidence;
  const hashNote =
    hashes?.pageHashBefore && hashes.pageHashAfter
      ? hashes.pageHashBefore === hashes.pageHashAfter
        ? 'the source page did not change'
        : 'the source page changed'
      : null;
  const hidden = item.class === 'suspect' || item.class === 'unknown';

  async function promote(e: FormEvent) {
    e.preventDefault();
    if (quote.trim() === '') return;
    setBusy('promote');
    setError(null);
    try {
      await client.promoteChange(api, build, item.id, quote.trim());
      setOpen(false);
      setQuote('');
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError && (err.code === 'QUOTE_NOT_VERIFIED' || err.status === 422)
          ? 'That quote is not in the source text of this build, so the change stays as it is. Copy the sentence exactly as the vendor page has it.'
          : err instanceof ApiError && err.status === 409
            ? `Not applicable: ${err.message}`
            : err instanceof Error
              ? err.message
              : 'Could not promote it.',
      );
    } finally {
      setBusy(null);
    }
  }

  async function demote() {
    setBusy('demote');
    setError(null);
    try {
      await client.demoteChange(api, build, item.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not demote it.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="change-row" data-class={item.class}>
      <div className="change-head">
        <Chip tone={TONE[item.class]}>{CLASS_LABEL[item.class]}</Chip>
        <Chip>{OP_LABEL[item.op] ?? item.op}</Chip>
        <Chip>{item.kind.replace(/_/g, ' ')}</Chip>
        {item.breaking ? <Chip tone="bad">Breaking</Chip> : null}
        {item.wordingOnly ? <Chip>wording only</Chip> : null}
        {(item.artifactRules ?? []).map((r) => (
          <Chip key={r} tone="warn">
            {r}
          </Chip>
        ))}
      </div>
      <p className="change-subject">
        <span className="mono">{subjectText(item)}</span>
        {item.subject.fieldPath ? (
          <>
            {' '}
            <span className="mono">{item.subject.fieldPath}</span>
          </>
        ) : null}
        {item.subject.location ? (
          <span className="faint small"> ({item.subject.location})</span>
        ) : null}
      </p>
      {item.breaking && item.breakingReason ? (
        <p className="small form-error">{item.breakingReason}</p>
      ) : null}
      <div className="change-values small">
        <div>
          <b>Before</b> <span className="mono">{valueText(item.before)}</span>
          {item.before?.quote ? (
            <blockquote className="quote">{item.before.quote}</blockquote>
          ) : null}
        </div>
        <div>
          <b>After</b> <span className="mono">{valueText(item.after)}</span>
          {item.after?.quote ? <blockquote className="quote">{item.after.quote}</blockquote> : null}
        </div>
      </div>
      <p className="small muted change-evidence">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer noopener">
            Vendor page
          </a>
        ) : (
          'No vendor page'
        )}
        {item.evidence?.anchor ? (
          <span className="mono"> #{item.evidence.anchor.replace(/^#/, '')}</span>
        ) : null}
        {hashNote ? <> · {hashNote}</> : null}
        {hashes?.pageHashBefore ? (
          <span className="mono faint">
            {' '}
            {hashes.pageHashBefore} → {hashes.pageHashAfter ?? '?'}
          </span>
        ) : null}
        {item.evidence?.changelog ? <> · {item.evidence.changelog}</> : null}
      </p>
      {item.promotedBy ? (
        <p className="small">
          <Chip tone="ok">Promoted by hand</Chip> by {item.promotedBy}
          {item.promotedAt ? ` on ${formatDate(item.promotedAt)}` : ''}.{' '}
          <Button disabled={busy !== null} onClick={() => void demote()}>
            {busy === 'demote' ? 'Demoting…' : 'Demote'}
          </Button>
          {item.computedClass && item.computedClass !== 'confirmed' ? (
            <span className="faint small"> (back to: {CLASS_LABEL[item.computedClass]})</span>
          ) : null}
        </p>
      ) : null}
      {hidden && !item.promotedBy ? (
        open ? (
          <form onSubmit={promote} className="change-promote" noValidate>
            <label htmlFor={`quote-${item.id}`} className="small">
              A quote from the vendor docs of this build that shows the change
            </label>
            <textarea
              id={`quote-${item.id}`}
              className="input"
              rows={3}
              value={quote}
              maxLength={1000}
              onChange={(e) => setQuote(e.target.value)}
            />
            <p className="faint small">
              Plume checks that the quote is in this build&apos;s source text. Users then see the
              change as confirmed.
            </p>
            <div className="row">
              <Button
                type="submit"
                variant="primary"
                disabled={busy !== null || quote.trim() === ''}
              >
                {busy === 'promote' ? 'Checking the quote…' : 'Promote to confirmed'}
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => setOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <p>
            <Button disabled={busy !== null} onClick={() => setOpen(true)}>
              Promote to confirmed…
            </Button>
          </p>
        )
      ) : null}
      {error ? (
        <p role="alert" className="form-error small">
          {error}
        </p>
      ) : null}
    </li>
  );
}
