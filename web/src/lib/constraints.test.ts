import { describe, expect, it } from 'vitest';
import { constraintParts } from './constraints';

describe('constraintParts', () => {
  it('shows nothing for null or empty constraints', () => {
    expect(constraintParts(null)).toEqual([]);
    expect(constraintParts(undefined)).toEqual([]);
    expect(constraintParts({})).toEqual([]);
  });

  it('writes an enum, ranges, a format and a default as plain pairs', () => {
    expect(
      constraintParts({
        enum: ['a', 'b', 3],
        minimum: 1,
        maximum: 100,
        minLength: 2,
        maxItems: 5,
        format: 'date-time',
        default: 'a',
      }),
    ).toEqual([
      { label: 'one of', value: 'a | b | 3' },
      { label: 'value', value: '1–100' },
      { label: 'length', value: '≥ 2' },
      { label: 'items', value: '≤ 5' },
      { label: 'format', value: 'date-time' },
      { label: 'default', value: 'a' },
    ]);
  });

  it('keeps a default of false or 0 and an exclusive bound of 0', () => {
    const parts = constraintParts({ default: false, exclusiveMinimum: 0 });
    expect(parts).toContainEqual({ label: 'default', value: 'false' });
    expect(parts).toContainEqual({ label: 'greater than', value: '0' });
  });

  it('cuts a long enum and a long pattern', () => {
    const many = constraintParts({ enum: Array.from({ length: 20 }, (_, i) => `v${i}`) });
    expect(many[0]?.value).toMatch(/\| \+8 more$/);
    const long = constraintParts({ pattern: 'x'.repeat(300) });
    expect(long[0]?.value.length).toBeLessThanOrEqual(80);
  });
});
