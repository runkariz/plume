import type { MappingReportKind, MappingReportStatus, MappingRoute } from '@/api/types';
import type { Tone } from '@/components';

export const MAPPING_STATUSES: MappingReportStatus[] = ['open', 'accepted', 'rejected', 'routed'];
export const MAPPING_KINDS: MappingReportKind[] = ['wrong', 'missing', 'model-field-missing'];
export const ROUTES: MappingRoute[] = ['plume', 'stream', 'owner'];

export const MAPPING_STATUS_LABEL: Record<MappingReportStatus, string> = {
  open: 'Open',
  accepted: 'Accepted',
  rejected: 'Rejected',
  routed: 'Routed',
};

export const MAPPING_STATUS_TONE: Record<MappingReportStatus, Tone> = {
  open: 'warn',
  accepted: 'ok',
  rejected: 'neutral',
  routed: 'info',
};

export const KIND_LABEL: Record<MappingReportKind, string> = {
  wrong: 'Wrong mapping',
  missing: 'Missing mapping',
  'model-field-missing': 'Field missing from the model',
};

/** Where a routed report goes, and why (the plan's weekly loop). */
export const ROUTE_LABEL: Record<MappingRoute, string> = {
  plume: 'Plume (the context missed the document)',
  stream: 'Stream (the field is not in the package)',
  owner: 'Owner (a proposal for the canonical model)',
};
export const ROUTE_SHORT: Record<MappingRoute, string> = {
  plume: 'Plume',
  stream: 'Stream',
  owner: 'Owner',
};

/** A value the web does not know (a newer server) is shown as written. */
export const mappingStatusLabel = (s: string): string =>
  (MAPPING_STATUS_LABEL as Record<string, string>)[s] ?? s;
export const mappingStatusTone = (s: string): Tone =>
  (MAPPING_STATUS_TONE as Record<string, Tone>)[s] ?? 'neutral';
export const kindLabel = (k: string): string => (KIND_LABEL as Record<string, string>)[k] ?? k;
export const routeShort = (r: string): string => (ROUTE_SHORT as Record<string, string>)[r] ?? r;
