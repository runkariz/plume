import type { HTMLAttributes } from 'react';

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={['card', className].filter(Boolean).join(' ')} {...rest} />;
}

export function Tile({
  value,
  label,
  tone,
}: {
  value: string | number;
  label: string;
  tone?: 'n' | 'c' | 'r' | 'u';
}) {
  return (
    <Card className="tile">
      <div className={`v${tone ? ` ${tone}` : ''}`}>{value}</div>
      <div className="k">{label}</div>
    </Card>
  );
}
