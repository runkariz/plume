import type { CoverageKind } from '@/api/types';

const LABEL: Record<CoverageKind, string> = {
  direct: 'direct',
  derived: 'derived',
  absent: 'absent',
};

/** A round API badge. direct = filled, derived = dashed ring, absent = faded. */
export function ApiAvatar({
  text,
  color,
  name,
  kind = 'direct',
  size = 34,
}: {
  text: string;
  color: string;
  name?: string;
  kind?: CoverageKind;
  size?: number;
}) {
  const label = name ? (kind === 'direct' ? name : `${name} (${LABEL[kind]})`) : undefined;
  const style =
    kind === 'direct'
      ? { background: color, color: '#fff' }
      : kind === 'derived'
        ? { background: 'transparent', color, border: `1.5px dashed ${color}` }
        : { background: 'var(--line2)', color: 'var(--faint)' };
  return (
    <span
      className={`avatar-api ${kind}`}
      style={{ width: size, height: size, fontSize: size * 0.4, ...style }}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {text.slice(0, 1)}
    </span>
  );
}
