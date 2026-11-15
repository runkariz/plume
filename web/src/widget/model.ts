import type { DraftIssue, ModelSnapshot } from '@/api/types';
import { apiLabel } from '@/lib/names';
import { withPaths } from '@/pages/models/fields';
import type { CallToolResult } from './protocol';

/** What a tool result means for the view. */
export type Shown =
  | { kind: 'model'; model: ModelSnapshot; link: string | null }
  | { kind: 'refused'; issues: DraftIssue[] }
  | { kind: 'pending'; status: string }
  | { kind: 'error'; message: string }
  | { kind: 'unrecognised' };

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

function looksLikeModel(v: unknown): v is ModelSnapshot {
  return (
    isObject(v) && Array.isArray(v.fields) && Array.isArray(v.inputs) && typeof v.id === 'string'
  );
}

/**
 * The model of a tool result: get_model / release_model / discard_model send the model itself, submit_model_draft
 * sends {accepted, snapshot_id, share_url, model}, get_generation sends the job and the model once it succeeded.
 * So the view reads `structuredContent.model ?? structuredContent`. A refused draft carries its issues instead.
 */
export function extractModel(result: CallToolResult): Shown {
  const text = result.content?.find((c) => c.type === 'text')?.text;
  if (result.isError) return { kind: 'error', message: text ?? 'The tool failed.' };
  const sc = result.structuredContent;
  if (!isObject(sc)) return { kind: 'unrecognised' };
  if (sc.accepted === false)
    return { kind: 'refused', issues: Array.isArray(sc.issues) ? (sc.issues as DraftIssue[]) : [] };
  const candidate = looksLikeModel(sc.model) ? sc.model : sc;
  if (!looksLikeModel(candidate)) {
    // get_generation while the job still runs: {status, ...} and no model yet
    if (typeof sc.status === 'string') return { kind: 'pending', status: sc.status };
    return { kind: 'unrecognised' };
  }
  const link =
    (typeof sc.share_url === 'string' && sc.share_url) ||
    (typeof candidate.shareUrl === 'string' && candidate.shareUrl) ||
    null;
  return { kind: 'model', model: normalise(candidate), link };
}

const NEUTRAL = '#6a655e';

/**
 * The tile of an API from what the server sent. Hosts and servers vary (an older server sent no `logo` in MCP
 * results at all), so a missing or odd value falls back to the first letter on a neutral colour instead of
 * breaking the view. The icon URL is always dropped: a relative /v1/... path cannot load in the sandboxed frame.
 */
export function safeLogo(a: {
  id?: string;
  shortName?: string;
  logo?: { text?: unknown; color?: unknown };
}): ModelSnapshot['inputs'][number]['logo'] {
  const text =
    typeof a.logo?.text === 'string' && a.logo.text.trim() !== ''
      ? a.logo.text
      : (a.shortName ?? a.id ?? '?').trim().slice(0, 1).toUpperCase() || '?';
  const color =
    typeof a.logo?.color === 'string' && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(a.logo.color.trim())
      ? a.logo.color.trim()
      : NEUTRAL;
  return { text, color, url: null };
}

/**
 * The model as the view shows it: the display names of the APIs, and no icon URLs (a relative /v1/... path cannot
 * load inside the sandboxed frame, so the letter tile is used).
 */
export function normalise(m: ModelSnapshot): ModelSnapshot {
  return withPaths({
    ...m,
    inputs: m.inputs.map((a) => ({
      ...a,
      shortName: apiLabel(a),
      logo: safeLogo(a),
    })),
  });
}
