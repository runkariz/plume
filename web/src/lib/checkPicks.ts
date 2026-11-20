/** A parameter value that picks one of several operations at the same METHOD + path ("method=ae.merchant.plan.list"). */
export interface CheckPick {
  key: string;
  value: string;
}

/**
 * The examples of an "ambiguous" check-call answer. The server's note ends with "(e.g. method=a, method=b, ...)":
 * those entries, in that order, at most `max`. A note without such a list gives none (nothing is guessed).
 */
export function picksFromNote(note: string | null | undefined, max = 6): CheckPick[] {
  const m = /\(e\.g\.\s*([^)]*)\)/.exec(note ?? '');
  if (!m?.[1]) return [];
  const out: CheckPick[] = [];
  for (const part of m[1].split(/,\s+/)) {
    const kv = /^([A-Za-z_][\w-]*)=([^\s<]\S*)$/.exec(part.trim());
    if (kv?.[1] && kv[2] && !out.some((p) => p.key === kv[1] && p.value === kv[2]))
      out.push({ key: kv[1], value: kv[2] });
    if (out.length >= max) break;
  }
  return out;
}

/** The params text ("limit, method=a") with this pick in it: an entry for the same key is replaced, others stay. */
export function withPick(paramsText: string, pick: CheckPick): string {
  const rest = paramsText
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s && s.split('=')[0]?.trim() !== pick.key);
  return [...rest, `${pick.key}=${pick.value}`].join(', ');
}
