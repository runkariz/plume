import { useState } from 'react';
import type { Notice, PackageWarning } from '@/api/types';
import { Card } from './Card';
import { Chip } from './Chip';

/**
 * What the package's warnings mean for a section, as a visible note (not an error): "Every request must be signed;
 * there is no ready auth option yet." Nothing when there are none. The text is the server's, shown as plain text.
 */
export function Notices({
  items,
  label = 'Notes on this package',
}: {
  items?: Notice[];
  label?: string;
}) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="notices" aria-label={label}>
      {items.map((n, i) => (
        <li key={`${n.code}-${i}`} className="notice" data-code={n.code}>
          <span className="notice-mark" aria-hidden>
            i
          </span>
          <span>
            <span className="sr-only">Note: </span>
            {n.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

const FIRST = 6;

/** The producer writes "code: text"; the code is its own chip, so it is not said twice. */
export const warningText = (w: PackageWarning): string =>
  w.text.startsWith(`${w.code}:`) ? w.text.slice(w.code.length + 1).trim() : w.text;

/** Every warning of the package manifest as a compact list: a code chip and the producer's text. Maintainers only. */
export function PackageWarningsCard({ warnings }: { warnings?: PackageWarning[] }) {
  const [all, setAll] = useState(false);
  if (!warnings || warnings.length === 0) return null;
  const shown = all ? warnings : warnings.slice(0, FIRST);
  return (
    <Card className="pad package-warnings" role="region" aria-label="Package warnings">
      <h2 className="h2-sm">
        Package warnings <span className="faint small">({warnings.length})</span>
      </h2>
      <p className="faint small">
        From the package&apos;s manifest. Only maintainers see this list.
      </p>
      <ul className="pw-list">
        {shown.map((w, i) => (
          <li key={`${w.code}-${i}`}>
            <Chip tone="warn">{w.code}</Chip> <span className="muted">{warningText(w)}</span>
          </li>
        ))}
      </ul>
      {warnings.length > FIRST ? (
        <div className="show-all">
          <button type="button" className="linkbtn" onClick={() => setAll((v) => !v)}>
            {all ? `Show the first ${FIRST}` : `Show all ${warnings.length}`}
          </button>
        </div>
      ) : null}
    </Card>
  );
}
