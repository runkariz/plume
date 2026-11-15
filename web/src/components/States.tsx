import type { ReactNode } from 'react';
import { Button } from './Button';

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="state">
      <div className="skeleton" style={{ width: 220, height: 14 }} aria-hidden />
      <div className="skeleton" style={{ width: 160, height: 14 }} aria-hidden />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="state error">
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {onRetry ? <Button onClick={onRetry}>Try again</Button> : null}
    </div>
  );
}
