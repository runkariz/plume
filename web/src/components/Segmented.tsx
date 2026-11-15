import { useId } from 'react';

export interface SegOption<T extends string> {
  value: T;
  label: string;
}

/** Radio-group style segmented control (arrow keys move the selection). */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  variant = 'seg',
}: {
  label: string;
  options: SegOption<T>[];
  value: T;
  onChange: (v: T) => void;
  variant?: 'seg' | 'pills';
}) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className={variant === 'seg' ? 'seg' : 'pills'}>
      {options.map((o) => (
        <label key={o.value} className={value === o.value ? 'on' : undefined}>
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          <span>{o.label}</span>
        </label>
      ))}
    </div>
  );
}
