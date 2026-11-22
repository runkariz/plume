import type { ConsentMethod } from '@/api/types';
import { Chip } from '@/components';

/** The consent filter of the lists: a method, "none" (stored before consent existed) or everything. */
export type ConsentFilter = ConsentMethod | 'none' | 'all';

export const CONSENT_FILTERS: { value: ConsentFilter; label: string }[] = [
  { value: 'all', label: 'Any consent' },
  { value: 'elicitation', label: 'Asked by Plume (elicitation)' },
  { value: 'llm_attested', label: 'Attested by the assistant' },
  { value: 'none', label: 'No consent record' },
];

export const isConsentFilter = (v: string | null): v is ConsentFilter =>
  v === 'elicitation' || v === 'llm_attested' || v === 'none' || v === 'all';

const LABEL: Record<string, string> = {
  elicitation: 'consent: elicitation',
  llm_attested: 'consent: assistant attested',
};
const HELP: Record<string, string> = {
  elicitation: 'Plume asked the user through the MCP client.',
  llm_attested: "The user's assistant showed the text and asked.",
};

/** Whether an item passes the filter. A method this app does not know matches only "all". */
export function matchesConsent(
  item: { consentMethod?: string | null },
  filter: ConsentFilter,
): boolean {
  if (filter === 'all') return true;
  if (filter === 'none') return !item.consentMethod;
  return item.consentMethod === filter;
}

/**
 * How the user agreed to a report or note, as a small chip: asked by Plume through the MCP client (elicitation), or
 * attested by the user's assistant. A report stored before consent existed says so.
 */
export function ConsentChip({ method }: { method: string | null | undefined }) {
  if (!method)
    return (
      <span title="Stored before consent was recorded">
        <Chip>no consent record</Chip>
      </span>
    );
  return (
    <span title={HELP[method] ?? method}>
      <Chip tone={method === 'elicitation' ? 'ok' : 'info'}>
        {LABEL[method] ?? `consent: ${method}`}
      </Chip>
    </span>
  );
}
