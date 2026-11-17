import type { DocumentOut } from '@/api/types';
import { constraintParts } from '@/lib/constraints';
import { Card } from './Card';

type Field = DocumentOut['fields'][number];

/** What the package says about the allowed values of a field, as small plain-text chips. */
function Constraints({ value }: { value: Field['constraints'] }) {
  const parts = constraintParts(value);
  if (parts.length === 0) return null;
  return (
    <ul className="constraints" aria-label="Constraints">
      {parts.map((p) => (
        <li key={p.label}>
          <span className="faint">{p.label}</span> <span className="mono">{p.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function FieldTable({ title, fields }: { title: string; fields: Field[] }) {
  return (
    <Card className="pad doc-fields" role="region" aria-label={title}>
      <h2 className="h2-sm">
        {title} <span className="faint small">({fields.length})</span>
      </h2>
      <table className="ev-fields">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Type</th>
            <th scope="col">Description</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => (
            <tr key={`${f.name}-${i}`}>
              <th scope="row" className="mono doc-field-name">
                {f.name}
                {f.required ? <span className="chip acc ev-req">required</span> : null}
              </th>
              <td className="mono">{f.type ?? '–'}</td>
              <td className="muted">
                {f.description ?? ''}
                <Constraints value={f.constraints} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
