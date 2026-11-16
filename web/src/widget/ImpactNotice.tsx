import { Banner } from '@/components';
import { impactLine } from '@/lib/impact';
import type { WidgetImpact } from './impact';

/**
 * The widget's summary of how newer docs touch the model or set: ONE line (the same words as the web), at most 5
 * compact rows of plain text; "Open in Plume" in the header leads to the rest (`impactUrl` is an API route, not a page).
 * It cannot fetch anything: everything comes in the tool result. Quiet when current, nothing at all when the server did not send an impact.
 */
export function ImpactNotice({ value, what }: { value: WidgetImpact | null; what: 'mappings' }) {
  const line = impactLine(value?.impact, what);
  if (!value || !line) return null;
  return (
    <div className="widget-impact" data-testid="widget-impact">
      <Banner
        tone={line.status === 'affected' ? 'warn' : 'accent'}
        title={`${line.icon} ${line.title}`}
      >
        {value.rows.length > 0 ? (
          <ul className="plain impact-rows compact" aria-label="What changed">
            {value.rows.map((r, i) => (
              <li key={`${r.api}/${r.field}/${i}`} className="small">
                {r.breaking ? <strong>Breaking: </strong> : null}
                {r.member ? <b>{r.member}: </b> : null}
                {r.text}
              </li>
            ))}
          </ul>
        ) : null}
      </Banner>
    </div>
  );
}
