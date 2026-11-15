import { Card } from './Card';

/** The package's source JSON, verbatim and untrusted: shown as text, collapsed unless asked, capped by the server. */
export function RawJson({
  raw,
  truncated,
  title = 'Source JSON, as in the package',
  label = 'Source JSON',
  open = false,
}: {
  raw: unknown;
  truncated?: boolean;
  title?: string;
  label?: string;
  open?: boolean;
}) {
  let body: string;
  try {
    body = JSON.stringify(raw, null, 2);
  } catch {
    return null;
  }
  return (
    <Card className="pad">
      <details className="doc-raw" open={open}>
        <summary>{title}</summary>
        {/* a scrollable region must be reachable with the keyboard */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
        <pre className="code payload" tabIndex={0} aria-label={label}>
          {body}
        </pre>
        {truncated ? (
          <p className="muted small">The server cut this JSON to its size limit.</p>
        ) : null}
      </details>
    </Card>
  );
}
