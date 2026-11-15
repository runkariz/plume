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

/** "2026-11-15T14:02:11.123Z" -> "14:02:11" (local time); "14:02:11" stays as is. */
export function formatClock(t: string): string {
  if (/^\d{2}:\d{2}:\d{2}$/.test(t)) return t;
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return t;
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, '0'))
    .join(':');
}

/** "b-6ff6063a275d40c14e4bcdd001f1c9ae" -> "b-6ff6063a275d"; short ids and dates stay as they are. */
export function shortBuild(id: string): string {
  return /^b-[0-9a-f]{20,}$/i.test(id) ? id.slice(0, 14) : id;
}

/** The model count to show: distinct names when the server sends them, else the number of model documents. */
export function modelCount(api: { models: number; modelNames?: number }): number {
  return api.modelNames ?? api.models;
}

export function formatScore(n: number, digits = 2): string {
  return n.toFixed(digits);
}
