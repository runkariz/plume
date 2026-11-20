import type { DocumentOut } from '@/api/types';
import { Link } from 'react-router-dom';
import { constraintParts } from '@/lib/constraints';
import { docHref } from '@/lib/docHref';
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

/**
 * The type of a field. When it refers to a model of the package (`modelId`) the model is a link to its page: the type
 * itself when it names the model ("address"), else the type followed by an arrow and the model ("array → state").
 * Without the API the model cannot be linked and the type is plain text.
 */
function FieldType({ api, field }: { api?: string; field: Field }) {
  const { modelId, type } = field;
  if (!api || !modelId) return <>{type ?? '–'}</>;
  const short = modelId.replace(/^model:/, '');
  const same = !type || type.toLowerCase() === short.toLowerCase();
  const link = (label: string) => (
    <Link to={docHref(api, modelId)} title={modelId} className="field-model">
      {label}
    </Link>
  );
  return same ? (
    link(type ?? modelId)
  ) : (
    <>
      {type} <span className="faint">→</span> {link(short)}
    </>
  );
}

export function FieldTable({
  title,
  fields,
  api,
}: {
  title: string;
  fields: Field[];
  /** The API the fields belong to: needed to link the models their types refer to. */
  api?: string;
}) {
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
              <td className="mono">
                <FieldType api={api} field={f} />
              </td>
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
