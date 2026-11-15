import type { HTMLAttributes } from 'react';

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={['card', className].filter(Boolean).join(' ')} {...rest} />;
}

export function Tile({
  value,
  label,
  tone,
  hint,
}: {
  value: string | number;
  label: string;
  tone?: 'n' | 'c' | 'r' | 'u';
  /** A small extra line, e.g. where the number comes from. */
  hint?: string;
}) {
  return (
    <Card className="tile">
      <div className={`v${tone ? ` ${tone}` : ''}`}>{value}</div>
      <div className="k">{label}</div>
      {hint ? <div className="k faint small">{hint}</div> : null}
    </Card>
  );
}
