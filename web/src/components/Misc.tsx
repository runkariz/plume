import { readableOn } from '@/lib/color';
import type { ReactNode } from 'react';

export function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' }) {
  return (
    <div className="metric">
      <span className="muted">{label}</span>
      <b className={tone}>{value}</b>
    </div>
  );
}

export function Kv({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="kv">
      <span className="muted">{label}</span>
      <span className={mono ? 'mono' : undefined}>{value}</span>
    </div>
  );
}

export function Logo({ text, color, size = 42 }: { text: string; color: string; size?: number }) {
  return (
    <div
      className="logo"
      style={{ background: color, color: readableOn(color), width: size, height: size }}
      aria-hidden
    >
      {text}
    </div>
  );
}

export function ScoreBar({ value, label }: { value: number; label: string }) {
  return (
    <span
      className="scorebar"
      role="img"
      aria-label={`${label} score ${Math.round(value * 100)} percent`}
    >
      <i style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </span>
  );
}
