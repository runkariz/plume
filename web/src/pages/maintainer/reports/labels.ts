import type { ReportStatus } from '@/api/types';
import type { Tone } from '@/components';

export const STATUSES: ReportStatus[] = [
  'open',
  'answered',
  'search-miss',
  'package-gap',
  'out-of-scope',
];

export const STATUS_LABEL: Record<ReportStatus, string> = {
  open: 'Open',
  answered: 'Answered',
  'search-miss': 'Search miss',
  'package-gap': 'Package gap',
  'out-of-scope': 'Out of scope',
};

export const STATUS_TONE: Record<ReportStatus, Tone> = {
  open: 'warn',
  answered: 'ok',
  'search-miss': 'info',
  'package-gap': 'bad',
  'out-of-scope': 'neutral',
};

/** The reasons of these reports are shown to readers (find_reported_questions), so they are public text. */
export const PUBLIC_REASON: ReportStatus[] = ['answered', 'out-of-scope'];

/** The most the server takes for a reason. */
export const REASON_MAX = 1000;

/** A status the web does not know (a newer server) is shown as written. */
export const statusLabel = (s: string): string => (STATUS_LABEL as Record<string, string>)[s] ?? s;
export const statusTone = (s: string): Tone =>
  (STATUS_TONE as Record<string, Tone>)[s] ?? 'neutral';

/** "ab12cd34": enough of the keyed hash to tell sessions apart. */
export const shortSession = (hash: string | null | undefined): string | null =>
  hash ? hash.slice(0, 8) : null;
