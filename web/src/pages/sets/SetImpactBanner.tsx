import { Banner, Chip } from '@/components';
import type { ModelSet } from '@/api/types';
import { IMPACT_ORDER, impactLine } from '@/lib/impact';
import { AffectedRows } from '../changes/AffectedRows';

/**
 * Leads a set page when the server says how newer docs touch it. The set's status is the worst of its members; the
 * members are listed worst first, each with its own status, so "3 affected" says where.
 */
export function SetImpactBanner({ set }: { set: ModelSet }) {
  const line = impactLine(set.impact, 'mappings');
  if (!line) return null;
  const members = [...(set.impact?.byMember ?? [])].sort(
    (a, b) => IMPACT_ORDER[a.status] - IMPACT_ORDER[b.status] || a.concept.localeCompare(b.concept),
  );
  return (
    <div className="stale-banner impact-banner" data-testid="impact-banner">
      <Banner
        tone={line.status === 'affected' ? 'warn' : 'accent'}
        title={`${line.icon} ${line.title}`}
      >
        {members.length > 0 ? (
          <ul className="plain impact-rows" aria-label="Impact per model">
            {members.map((m) => {
              const l = impactLine({
                status: m.status,
                affectedCount: m.affectedCount,
                breakingCount: 0,
              });
              return (
                <li key={m.concept}>
                  <b>{m.concept}</b>{' '}
                  {l ? (
                    <Chip tone={l.tone === 'neutral' ? undefined : l.tone}>
                      <span aria-hidden="true">{l.icon} </span>
                      {l.chip}
                    </Chip>
                  ) : (
                    <span className="faint small">Current</span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null}
        {line.status === 'affected' ? (
          <AffectedRows id={set.id} kind="set" count={set.impact?.affectedCount} />
        ) : null}
        {line.status === 'unknown' ? (
          <span className="muted">
            A build behind this set has no release notes, so Plume cannot say whether newer docs
            touch it.
          </span>
        ) : null}
      </Banner>
    </div>
  );
}
