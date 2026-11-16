import type { FieldConstraints } from '@/api/types';

const MAX_VALUE = 80;
const MAX_ENUM = 12;

/** A verbatim value from a package as short plain text (objects are written as JSON, cut when long). */
function show(v: unknown): string {
  let t: string;
  if (typeof v === 'string') t = v;
  else if (typeof v === 'number' || typeof v === 'boolean' || v === null) t = String(v);
  else {
    try {
      t = JSON.stringify(v) ?? '';
    } catch {
      t = '';
    }
  }
  return t.length > MAX_VALUE ? `${t.slice(0, MAX_VALUE - 1)}…` : t;
}

const has = (v: unknown) => v !== undefined && v !== null && v !== '';

/** A range as "min–max", "≥ min" or "≤ max". */
function range(lo: unknown, hi: unknown): string | null {
  if (has(lo) && has(hi)) return `${show(lo)}–${show(hi)}`;
  if (has(lo)) return `≥ ${show(lo)}`;
  if (has(hi)) return `≤ ${show(hi)}`;
  return null;
}

export interface ConstraintPart {
  label: string;
  value: string;
}

/**
 * What a field's constraints say, as label/value pairs for plain-text display. Nothing is added: a constraint the
 * package leaves out is not shown.
 */
export function constraintParts(c: FieldConstraints | null | undefined): ConstraintPart[] {
  if (!c) return [];
  const out: ConstraintPart[] = [];
  if (Array.isArray(c.enum) && c.enum.length > 0) {
    const shown = c.enum.slice(0, MAX_ENUM).map(show).join(' | ');
    const more = c.enum.length - MAX_ENUM;
    out.push({ label: 'one of', value: more > 0 ? `${shown} | +${more} more` : shown });
  }
  const value = range(c.minimum, c.maximum);
  if (value) out.push({ label: 'value', value });
  if (has(c.exclusiveMinimum)) out.push({ label: 'greater than', value: show(c.exclusiveMinimum) });
  if (has(c.exclusiveMaximum)) out.push({ label: 'less than', value: show(c.exclusiveMaximum) });
  const length = range(c.minLength, c.maxLength);
  if (length) out.push({ label: 'length', value: length });
  const items = range(c.minItems, c.maxItems);
  if (items) out.push({ label: 'items', value: items });
  if (has(c.format)) out.push({ label: 'format', value: show(c.format) });
  if (has(c.pattern)) out.push({ label: 'pattern', value: show(c.pattern) });
  if (c.default !== undefined) out.push({ label: 'default', value: show(c.default) });
  return out;
}
