const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-11-14" -> "14 Nov 2026" (no timezone shifts: the date is parsed as plain text). */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${m[3]} ${month} ${m[1]}` : iso;
}

const CATEGORY_LABELS: Record<string, string> = {
  'e-commerce': 'E-commerce',
  'developer-tools': 'Developer tools',
  other: 'Other',
};

/** Shows a producer category key: known keys get their label, others are title-cased ("dev_tools" -> "Dev tools"). */
export function categoryLabel(key: string): string {
  const known = CATEGORY_LABELS[key];
  if (known) return known;
  const text = key.replace(/_/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Other';
}

/** 47 -> "47 ms", 3.2 -> "3.2 ms", 0.4 -> "0.4 ms". */
export function formatMs(ms: number): string {
  return `${ms >= 10 ? Math.round(ms) : Math.round(ms * 10) / 10} ms`;
}

export function formatScore(n: number, digits = 2): string {
  return n.toFixed(digits);
}
