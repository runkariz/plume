import { useId, type InputHTMLAttributes } from 'react';

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  mono?: boolean;
};

/** A labelled input: the label is always associated, the hint is announced with the input. */
export function Field({ label, hint, mono, className, ...rest }: Props) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        aria-describedby={hintId}
        className={['input', mono ? 'mono' : '', className].filter(Boolean).join(' ')}
        {...rest}
      />
      {hint ? (
        <span id={hintId} className="hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
