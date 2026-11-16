import { Link } from 'react-router-dom';
import type { ModelSnapshot } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Banner } from '@/components';
import { impactLine } from '@/lib/impact';
import { AffectedRows } from '../changes/AffectedRows';

/**
 * Leads a model page instead of the stale mark, when the server says how newer docs touch it (`impact`). Quiet when
 * current. `unknown` never reads as unaffected. Regenerate is for maintainers (and the owner of an unreleased copy).
 */
export function ImpactBanner({ snap }: { snap: ModelSnapshot }) {
  const maintainer = useIsMaintainer();
  const line = impactLine(snap.impact);
  if (!line) return null;
  const regenerate = (
    <div className="row">
      <Link
        className="btn primary"
        to={`/models/suggest?apis=${snap.inputs.map((a) => a.id).join(',')}&regenerate=${encodeURIComponent(snap.concept ?? snap.name)}`}
      >
        Regenerate
      </Link>
      <span className="faint small">Opens a new generation session for {snap.name}.</span>
    </div>
  );
  return (
    <div className="stale-banner impact-banner" data-testid="impact-banner">
      <Banner
        tone={line.status === 'affected' ? 'warn' : 'accent'}
        title={`${line.icon} ${line.title}`}
      >
        {line.status === 'affected' ? (
          <>
            <AffectedRows id={snap.id} kind="model" />
            {maintainer || !snap.official ? regenerate : null}
          </>
        ) : line.status === 'unknown' ? (
          <span className="muted">
            A build this model was made from, or one after it, has no release notes, so Plume cannot
            say whether newer docs touch it.
          </span>
        ) : (
          <span className="muted">
            Newer docs exist; none of the changes touches a field this model cites.
          </span>
        )}
      </Banner>
    </div>
  );
}
