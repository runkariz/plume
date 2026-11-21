import type { Report, ReportNote, ReportStatus } from '@/api/types';

/** Reported questions of the mock server (maintainer): redacted text, like the real one. */
const t = (day: number) => `2026-11-${String(day).padStart(2, '0')}T10:00:00Z`;

const note = (
  id: string,
  kind: string,
  text: string,
  day: number,
  client: string,
  session: string,
  redactions = 0,
): ReportNote => ({
  id,
  kind,
  text,
  createdAt: t(day),
  clientName: client,
  sessionHash: session,
  build: 'b-2026-11-14',
  redactions,
});

export function seedReports(): Report[] {
  return [
    {
      id: 'rq-1a2b3c4d5e',
      api: 'shopify',
      build: 'b-2026-11-14',
      question:
        'How do I page through all orders when page_info is not accepted with other filters?',
      whatWasTried:
        'search_docs for "page_info filters"; check_call GET /orders.json with page_info and status.',
      whatWasMissing: 'Which filters can be combined with page_info; the docs do not say.',
      status: 'open',
      reason: null,
      reportCount: 4,
      noteCount: 3,
      createdAt: t(14),
      updatedAt: t(18),
      clientName: 'claude-code 2.1',
      sessionHash: '9f8e7d6c5b4a3921',
      redactions: 0,
      notes: [
        note(
          'n1',
          'duplicate',
          'Paging orders with page_info and created_at_min fails',
          15,
          'claude-code 2.1',
          '11aa22bb33cc44dd',
        ),
        note(
          'n2',
          'note',
          'Also happens with the status filter. Account [account] hit it.',
          16,
          'cursor',
          '55ee66ff77aa88bb',
          1,
        ),
        note(
          'n3',
          'duplicate',
          'page_info next link and fields param',
          18,
          'claude-desktop',
          'cc99dd88ee77ff66',
        ),
      ],
    },
    {
      id: 'rq-9z8y7x6w5v',
      api: 'shopify',
      build: 'b-2026-11-14',
      question: 'What is the rate limit of the GraphQL Admin API?',
      whatWasTried: 'find_fact rate_limit graphql',
      whatWasMissing: 'This package documents REST only.',
      status: 'out-of-scope',
      reason: 'This package covers the REST Admin API; GraphQL is a separate API.',
      reportCount: 2,
      noteCount: 1,
      createdAt: t(12),
      updatedAt: t(17),
      clientName: 'claude-code 2.1',
      sessionHash: '0a1b2c3d4e5f6071',
      redactions: 0,
      notes: [note('n4', 'duplicate', 'GraphQL cost limits', 17, 'cursor', '55ee66ff77aa88bb')],
    },
    {
      id: 'rq-5t4s3r2q1p',
      api: 'stripe',
      build: 'b-2026-11-10',
      question: 'Token [token] is rejected by /v1/balance: which header carries the key?',
      whatWasTried: 'get_auth_scheme api-key',
      whatWasMissing: null,
      status: 'answered',
      reason: 'The Authorization header carries the key as a Bearer token.',
      reportCount: 1,
      noteCount: 0,
      createdAt: t(11),
      updatedAt: t(13),
      clientName: null,
      sessionHash: null,
      redactions: 1,
      notes: [],
    },
    {
      id: 'rq-7m6n5b4v3c',
      api: 'shopify',
      build: 'b-2026-11-14',
      question: 'search_docs finds nothing for "inventory level adjust by delta"',
      whatWasTried: 'search_docs with three phrasings',
      whatWasMissing: 'The adjust endpoint, which exists in the package.',
      status: 'search-miss',
      reason:
        'Adjust is documented as "inventory_levels/adjust.json"; synonyms added to the extraction.',
      reportCount: 1,
      noteCount: 0,
      createdAt: t(9),
      updatedAt: t(10),
      clientName: 'cursor',
      sessionHash: 'aa00bb11cc22dd33',
      redactions: 0,
      notes: [],
    },
  ];
}

const ORDER = (a: Report, b: Report) =>
  b.reportCount - a.reportCount || b.updatedAt.localeCompare(a.updatedAt);

export function listReports(all: Report[], api: string | null, status: string | null): Report[] {
  return all
    .filter((r) => (!api || r.api === api) && (!status || r.status === status))
    .map((r) => ({ ...r, notes: undefined }))
    .sort(ORDER);
}

export const isStatus = (v: unknown): v is ReportStatus =>
  v === 'open' ||
  v === 'answered' ||
  v === 'search-miss' ||
  v === 'package-gap' ||
  v === 'out-of-scope';
