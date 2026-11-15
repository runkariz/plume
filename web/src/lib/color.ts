function channel(c: number): number {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance of #rgb / #rrggbb; null when the value is not a hex colour (or not a string at all). */
export function luminance(hex: string): number | null {
  if (typeof hex !== 'string') return null; // server data: a missing colour must not crash the page
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m || !m[1]) return null;
  const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join('') : m[1];
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number | null {
  const la = luminance(a);
  const lb = luminance(b);
  if (la === null || lb === null) return null;
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const LIGHT = '#ffffff';
const DARK = '#1c1b1a';

/** The text colour (white or near-black) with the better contrast on a background chosen by the data. */
export function readableOn(bg: string): string {
  const w = contrastRatio(LIGHT, bg);
  const d = contrastRatio(DARK, bg);
  if (w === null || d === null) return LIGHT;
  return w >= d ? LIGHT : DARK;
}
