import { Link } from 'react-router-dom';
import type { DocsUpdated } from '@/api/types';
import { formatDate } from '@/lib/format';

/** "Docs updated 14 Nov 2026: 3 changes, 1 breaking": the visible, non-wording changes of the latest build. */
export function docsUpdatedText(d: DocsUpdated): string | null {
  const n = d.confirmed + d.likely;
  if (n <= 0) return null;
  const parts = [`${n} ${n === 1 ? 'change' : 'changes'}`];
  if (d.breaking > 0) parts.push(`${d.breaking} breaking`);
  return `Docs updated ${formatDate(d.at)}: ${parts.join(', ')}`;
}

/**
 * The badge on an API: text and a glyph (never colour alone), a link to the Changes tab. Shown only when the server
 * says docs were updated (`docsUpdated` non-null) and there is something besides wording to show.
 */
export function DocsUpdatedBadge({
  api,
  docsUpdated,
}: {
  api: string;
  docsUpdated?: DocsUpdated | null;
}) {
  const text = docsUpdated ? docsUpdatedText(docsUpdated) : null;
  if (!docsUpdated || !text) return null;
  return (
    <Link
      className={`docs-badge${docsUpdated.breaking > 0 ? ' breaking' : ''}`}
      to={`/apis/${encodeURIComponent(api)}?section=changes&build=${encodeURIComponent(docsUpdated.build)}`}
    >
      <span aria-hidden="true">{docsUpdated.breaking > 0 ? '⚠' : '↻'} </span>
      {text}
    </Link>
  );
}
