import type { Impact, ImpactStatus } from '@/api/types';

/**
 * How newer docs touch a model or set, in words. The same wording everywhere (lists, pages, the widget). `current` is
 * quiet (null: nothing to say); `unknown` never reads as "unaffected": a build in between has no notes.
 */
export interface ImpactLine {
  status: ImpactStatus;
  tone: 'warn' | 'info' | 'neutral';
  /** A glyph that is never the only carrier of the meaning (the text says it too). */
  icon: string;
  /** Short, for a chip. */
  chip: string;
  /** A sentence, for a banner. */
  title: string;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function impactLine(
  impact: Impact | null | undefined,
  what = 'mappings',
): ImpactLine | null {
  if (!impact) return null;
  switch (impact.status) {
    case 'affected': {
      const n = plural(impact.affectedCount, what.replace(/s$/, ''), what);
      const b = impact.breakingCount > 0 ? ` (${impact.breakingCount} breaking)` : '';
      return {
        status: 'affected',
        tone: 'warn',
        icon: '⚠',
        chip: `${impact.affectedCount} affected${b}`,
        title: `${n} affected${b}`,
      };
    }
    case 'updated_unaffected':
      return {
        status: 'updated_unaffected',
        tone: 'info',
        icon: '↻',
        chip: 'Docs updated, unaffected',
        title: `Docs updated, your ${what} are unaffected`,
      };
    case 'unknown':
      return {
        status: 'unknown',
        tone: 'neutral',
        icon: '?',
        chip: 'Not checked against newer docs',
        title: 'Not checked against newer docs',
      };
    default:
      return null;
  }
}

/** The set's status per member, worst first (affected > unknown > updated_unaffected > current) for display. */
export const IMPACT_ORDER: Record<ImpactStatus, number> = {
  affected: 0,
  unknown: 1,
  updated_unaffected: 2,
  current: 3,
};
