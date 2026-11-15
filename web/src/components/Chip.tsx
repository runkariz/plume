import type { ReactNode } from 'react';

export type Tone = 'neutral' | 'ok' | 'info' | 'warn' | 'bad' | 'acc';

export function Chip({
  tone = 'neutral',
  dot = false,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`chip ${tone === 'neutral' ? '' : tone}`.trim()}>
      {dot ? <span className="dot" aria-hidden /> : null}
      {children}
    </span>
  );
}
