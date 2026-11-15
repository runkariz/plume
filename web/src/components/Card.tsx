import type { HTMLAttributes } from 'react';

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={['card', className].filter(Boolean).join(' ')} {...rest} />;
}

export function Tile({ value, label }: { value: string | number; label: string }) {
  return (
    <Card className="tile">
      <div className="v">{value}</div>
      <div className="k">{label}</div>
    </Card>
  );
}
