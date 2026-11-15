import type { StaleInput } from '@/api/types';
import { Chip } from '@/components';
import { shortBuild } from '@/lib/format';
import { apiLabel } from '@/lib/names';

/** "Stale: built on older docs of Shopify, WooCommerce": the docs of a pinned API changed after the model was built. */
export function StaleChip({ inputs, short = false }: { inputs?: StaleInput[]; short?: boolean }) {
  if (!inputs || inputs.length === 0) return <Chip tone="warn">Stale</Chip>;
  const names = inputs.map((i) => apiLabel({ id: i.api })).join(', ');
  const detail = inputs
    .map(
      (i) =>
        `${apiLabel({ id: i.api })}: built on ${shortBuild(i.pinned)}, now ${shortBuild(i.current)}`,
    )
    .join('; ');
  return (
    <span title={detail}>
      <Chip tone="warn">{short ? 'Stale' : `Stale: built on older docs of ${names}`}</Chip>
    </span>
  );
}
