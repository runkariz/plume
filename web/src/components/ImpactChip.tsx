import type { Impact } from '@/api/types';
import { impactLine } from '@/lib/impact';
import { Chip } from './Chip';

/**
 * The impact of newer docs on a model or set, as a chip (text and glyph, never colour alone). Quiet when current.
 * The server says it; absent `impact` renders nothing (the caller falls back to the stale mark).
 */
export function ImpactChip({ impact }: { impact: Impact | null | undefined }) {
  const line = impactLine(impact);
  if (!line) return null;
  return (
    <Chip tone={line.tone === 'neutral' ? undefined : line.tone}>
      <span aria-hidden="true">{line.icon} </span>
      {line.chip}
    </Chip>
  );
}
