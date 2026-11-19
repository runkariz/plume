import type { FieldConversion } from '@/api/types';
import { Chip } from '@/components';

/** What each kind of conversion says in a few words; a kind this app does not know is shown as written. */
const KIND_LABEL: Record<string, string> = {
  'money-minor': 'money in minor units',
  'money-decimal': 'money as decimal',
  'money-decimal-string': 'money as decimal string',
  'currency-separate': 'currency in another field',
  enum: 'enum map',
  datetime: 'date/time format',
  'id-type': 'id type',
  'array-vs-single': 'array vs single',
  cardinality: 'cardinality',
  embedded: 'embedded',
  derived: 'derived from name',
  'meta-entry': 'meta entry',
  split: 'split or sum',
  other: 'conversion',
};

export const conversionLabel = (kind: string) => KIND_LABEL[kind] ?? kind;

/** The map of an enum conversion as entries, API value first; anything that is not a text-to-text map is left out. */
export function mapEntries(c: FieldConversion): [string, string][] {
  return Object.entries(c.map ?? {}).flatMap(([k, v]) =>
    typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
      ? [[k, String(v)] as [string, string]]
      : [],
  );
}

/** Whether there is more to say than the kind: a map, a format or a note. */
const hasMore = (c: FieldConversion) =>
  mapEntries(c).length > 0 || Boolean(c.format?.trim()) || Boolean(c.note?.trim());

function Body({ c, label }: { c: FieldConversion; label: string }) {
  const entries = mapEntries(c);
  return (
    <div className="conv-body">
      {c.format ? (
        <p className="small">
          <span className="faint">{c.kind === 'meta-entry' ? 'key:' : 'format:'}</span>{' '}
          <span className="mono">{c.format}</span>
        </p>
      ) : null}
      {entries.length ? (
        <ul className="conv-map" aria-label={`${label}: API value to canonical value`}>
          {entries.map(([from, to]) => (
            <li key={from}>
              <span className="mono">{from}</span> <span className="faint">→</span>{' '}
              <span className="mono">{to}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {c.note ? <p className="small muted">{c.note}</p> : null}
    </div>
  );
}

/**
 * A small chip with the kind of conversion a value needs, opening to the enum map, the format and the note.
 * Nothing when the model states no conversion for the field (every model before the server sent them).
 */
export function ConversionChip({ conversion }: { conversion: FieldConversion | null | undefined }) {
  if (!conversion || typeof conversion.kind !== 'string' || !conversion.kind) return null;
  const label = conversionLabel(conversion.kind);
  if (!hasMore(conversion))
    return (
      <div className="conv">
        <Chip tone="info">{label}</Chip>
      </div>
    );
  return (
    <details className="conv">
      <summary>
        <Chip tone="info">{label}</Chip>
      </summary>
      <Body c={conversion} label={label} />
    </details>
  );
}

/** The conversion in full, for the mapping detail: the kind, then the key or format, the map and the note. */
export function ConversionDetail({
  conversion,
}: {
  conversion: FieldConversion | null | undefined;
}) {
  if (!conversion || typeof conversion.kind !== 'string' || !conversion.kind) return null;
  const label = conversionLabel(conversion.kind);
  return (
    <div className="dl">
      <div className="dl-k">Conversion</div>
      <div>
        <Chip tone="info">{label}</Chip>
      </div>
      <Body c={conversion} label={label} />
    </div>
  );
}
