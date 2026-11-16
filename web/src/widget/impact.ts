import type { Impact, ImpactStatus } from '@/api/types';

/** One compact row of what newer docs changed for a model: one plain line of text (no fetch is possible here). */
export interface ImpactRow {
  field: string;
  api: string;
  member: string | null;
  op: string;
  breaking: boolean;
  text: string;
}

/** The impact of newer docs as the MCP result carries it: the summary, at most 5 rows, and where to read the rest. */
export interface WidgetImpact {
  impact: Impact;
  rows: ImpactRow[];
  /** The API route with every affected mapping (`impactUrl`): an API path, not a page of the web app. */
  url: string | null;
}

const STATUSES: ImpactStatus[] = ['current', 'updated_unaffected', 'affected', 'unknown'];
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const str = (v: unknown) => (typeof v === 'string' ? v : '');

function impactOf(v: unknown): Impact | null {
  if (!isObject(v) || !STATUSES.includes(v.status as ImpactStatus)) return null;
  const byMember = Array.isArray(v.byMember)
    ? v.byMember.flatMap((m) =>
        isObject(m) && typeof m.concept === 'string' && STATUSES.includes(m.status as ImpactStatus)
          ? [
              {
                concept: m.concept,
                status: m.status as ImpactStatus,
                affectedCount: num(m.affectedCount),
              },
            ]
          : [],
      )
    : undefined;
  return {
    status: v.status as ImpactStatus,
    affectedCount: num(v.affectedCount),
    breakingCount: num(v.breakingCount),
    ...(byMember ? { byMember } : {}),
  };
}

function rowsOf(v: unknown): ImpactRow[] {
  if (!Array.isArray(v)) return [];
  return v
    .flatMap((r) => {
      if (!isObject(r) || str(r.text) === '') return [];
      return [
        {
          field: str(r.field),
          api: str(r.api),
          member: str(r.member) || null,
          op: str(r.op),
          breaking: r.breaking === true,
          text: str(r.text),
        },
      ];
    })
    .slice(0, 5);
}

/**
 * The impact of a tool result: the model's (or set's) own `impact`, else `structuredContent.impact`; the compact rows
 * (`impactRows`, or `impact.rows`) and `impactUrl`. Anything of another shape is dropped: a view never shows a half
 * summary, and the absence of `impact` means the server did not say (an older server: the view shows nothing new).
 */
export function readImpact(sc: Record<string, unknown>, own?: unknown): WidgetImpact | null {
  const fromSc = isObject(sc.impact) ? sc.impact : null;
  const impact = impactOf(fromSc) ?? impactOf(own);
  if (!impact) return null;
  const src = isObject(fromSc) ? fromSc : isObject(own) ? own : null;
  return {
    impact,
    rows: rowsOf(src?.rows ?? sc.impactRows),
    url: str(src?.impactUrl) || str(sc.impactUrl) || null,
  };
}
