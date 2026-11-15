import { categoryLabel, formatClock, formatDate, formatMs, shortBuild } from './format';

describe('format helpers', () => {
  it('formats dates without timezone shifts', () => {
    expect(formatDate('2026-11-14')).toBe('14 Nov 2026');
    expect(formatDate('2026-11-14T23:59:59Z')).toBe('14 Nov 2026');
    expect(formatDate('garbage')).toBe('garbage');
  });
  it('shows a category key with a label', () => {
    expect(categoryLabel('e-commerce')).toBe('E-commerce');
    expect(categoryLabel('developer-tools')).toBe('Developer tools');
    expect(categoryLabel('dev_ops')).toBe('Dev ops');
    expect(categoryLabel('other')).toBe('Other');
    expect(categoryLabel('')).toBe('Other');
  });
  it('formats clock times from ISO strings and keeps HH:MM:SS', () => {
    expect(formatClock('14:02:11')).toBe('14:02:11');
    expect(formatClock('2026-11-15T14:02:11')).toBe('14:02:11'); // local time, no zone suffix
    expect(formatClock('not a time')).toBe('not a time');
  });
  it('shortens long build ids only', () => {
    expect(shortBuild('b-6ff6063a275d40c14e4bcdd001f1c9ae')).toBe('b-6ff6063a275d');
    expect(shortBuild('2026-11-14')).toBe('2026-11-14');
    expect(shortBuild('b-abc')).toBe('b-abc');
  });
  it('formats milliseconds', () => {
    expect(formatMs(47.3)).toBe('47 ms');
    expect(formatMs(3.24)).toBe('3.2 ms');
    expect(formatMs(0.05)).toBe('0.1 ms');
  });
});
