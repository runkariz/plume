import { useState } from 'react';
import { useApiBaseUrl } from '@/api/context';
import type { CoverageKind } from '@/api/types';
import { readableOn } from '@/lib/color';
import { iconSrc } from '@/lib/icon';

const LABEL: Record<CoverageKind, string> = {
  direct: 'direct',
  derived: 'derived',
  absent: 'absent',
};

/**
 * A round API badge: the package's own icon (`logo.url`, a path on the API) or, without one or if it fails, the
 * first letter. direct = filled / full colour, derived = dashed ring, absent = faded.
 */
export function ApiAvatar({
  text,
  color,
  name,
  kind = 'direct',
  size = 34,
  url,
}: {
  text: string;
  color: string;
  name?: string;
  kind?: CoverageKind;
  size?: number;
  /** `logo.url` from the API. Anything that is not a /v1/ path on the API is ignored (letter instead). */
  url?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  const base = useApiBaseUrl();
  const src = iconSrc(url, base);
  const label = name ? (kind === 'direct' ? name : `${name} (${LABEL[kind]})`) : undefined;
  const common = {
    role: label ? ('img' as const) : undefined,
    'aria-label': label,
    'aria-hidden': label ? undefined : true,
  };
  if (src && !failed)
    return (
      <span
        className={`avatar-api icon ${kind}`}
        style={{
          width: size,
          height: size,
          padding: Math.max(2, Math.round(size * 0.14)), // px: a % would be relative to the parent
          ...(kind === 'derived' ? { borderColor: color } : {}),
        }}
        {...common}
      >
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      </span>
    );
  const style =
    kind === 'direct'
      ? { background: color, color: readableOn(color) }
      : kind === 'derived'
        ? { background: 'transparent', color, border: `1.5px dashed ${color}` }
        : { background: 'var(--line2)', color: 'var(--faint)' };
  return (
    <span
      className={`avatar-api ${kind}`}
      style={{ width: size, height: size, fontSize: size * 0.4, ...style }}
      {...common}
    >
      {text.slice(0, 1)}
    </span>
  );
}
