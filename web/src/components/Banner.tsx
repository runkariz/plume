import type { ReactNode } from 'react';
import { CheckIcon } from '@/icons';

/** A tinted message box: "Nothing goes live yet" (accent), "Quality gate passed" (ok), blocked (bad). */
export function Banner({
  tone,
  title,
  children,
  icon = false,
}: {
  tone: 'ok' | 'bad' | 'accent' | 'warn';
  title: string;
  children?: ReactNode;
  icon?: boolean;
}) {
  return (
    <div className={`banner ${tone}`} role={tone === 'bad' ? 'alert' : 'status'}>
      {icon ? (
        <span className="banner-icon" aria-hidden>
          <CheckIcon width={18} height={18} />
        </span>
      ) : null}
      <div>
        <h3>{title}</h3>
        {children ? <p>{children}</p> : null}
      </div>
    </div>
  );
}
