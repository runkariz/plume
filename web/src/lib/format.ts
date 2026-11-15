const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-11-14" -> "14 Nov 2026" (no timezone shifts: the date is parsed as plain text). */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${m[3]} ${month} ${m[1]}` : iso;
}

export function formatScore(n: number, digits = 2): string {
  return n.toFixed(digits);
}
