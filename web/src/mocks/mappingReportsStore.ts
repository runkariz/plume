import type { MappingReport, ReportNote, VerifiedMapping } from '@/api/types';

/** Mapping reports of the mock server (maintainer): redacted text, the validator's answer, like the real one. */
const t = (day: number) => `2026-11-${String(day).padStart(2, '0')}T10:00:00Z`;
const QUOTE = 'Total amount billed for the order.';

const note = (id: string, kind: string, text: string, day: number, client: string): ReportNote => ({
  id,
  kind,
  text,
  createdAt: t(day),
  clientName: client,
  sessionHash: null,
  redactions: 0,
});

export function seedMappingReports(): MappingReport[] {
  return [
    {
      id: 'mr-1a2b3c4d5e',
      concept: 'inventory/stock',
      conceptName: 'Inventory',
      modelId: 'snap_8f3a21',
      api: 'shopify',
      build: 'b-2026-11-14',
      canonicalField: 'quantity_available',
      kind: 'wrong',
      status: 'open',
      route: null,
      reason: null,
      problem:
        'quantity_available is mapped to the total over all warehouses, but a client needs the quantity at one location.',
      currentMapping: 'variants[].inventory_quantity, the total over all locations',
      suggestion: {
        paths: ['inventory_levels[].available'],
        fetch: 'GET /admin/api/{version}/inventory_levels.json',
        evidence: [{ docId: 'endpoint:GET~/orders.json', quote: QUOTE, noQuote: null }],
      },
      validation: { ok: true, reason: null },
      verified: null,
      reportCount: 3,
      noteCount: 2,
      createdAt: t(18),
      updatedAt: t(20),
      clientName: 'claude-code 2.1',
      sessionHash: null,
      redactions: 0,
      notes: [
        note('n1', 'duplicate', 'Same problem with the Shopify inventory total', 19, 'cursor'),
        note(
          'n2',
          'note',
          'Per-location quantities are needed for the warehouse view.',
          20,
          'claude-desktop',
        ),
      ],
    },
    {
      id: 'mr-9z8y7x6w5v',
      concept: 'product/variant',
      conceptName: 'Product',
      modelId: null,
      api: 'woocommerce',
      build: 'b-2026-11-14',
      canonicalField: 'variants[].id',
      kind: 'wrong',
      status: 'open',
      route: null,
      reason: null,
      problem:
        'variants[].id is mapped to variationValueId, which is the id of an option value, not of the variant.',
      currentMapping: 'variationValueId',
      suggestion: null,
      validation: {
        ok: false,
        reason: 'FIELD_NOT_FOUND: variation_id is not a field of the WooCommerce package',
      },
      verified: null,
      reportCount: 1,
      noteCount: 0,
      createdAt: t(19),
      updatedAt: t(19),
      clientName: 'cursor',
      sessionHash: null,
      redactions: 0,
      notes: [],
    },
    {
      id: 'mr-5t4s3r2q1p',
      concept: 'inventory/stock',
      conceptName: 'Inventory',
      modelId: 'snap_8f3a21',
      api: 'shopify',
      build: 'b-2026-11-14',
      canonicalField: 'tracked',
      kind: 'missing',
      status: 'accepted',
      route: null,
      reason: 'Confirmed in the docs: inventory_management tells whether stock is tracked.',
      problem: 'The canonical field tracked has no mapping on Shopify.',
      currentMapping: null,
      suggestion: {
        paths: ['variants[].inventory_management'],
        fetch: null,
        evidence: [
          {
            docId: 'endpoint:GET~/orders.json',
            quote: null,
            noQuote: 'the description is only a label (Inventory management)',
          },
        ],
      },
      validation: { ok: true, reason: null },
      verified: {
        id: 'vm-77aa88bb99',
        reportId: 'mr-5t4s3r2q1p',
        build: 'b-2026-11-14',
        validatedAt: t(20),
        suspended: false,
        suspendedReason: null,
      },
      reportCount: 2,
      noteCount: 0,
      createdAt: t(15),
      updatedAt: t(17),
      clientName: 'claude-code 2.1',
      sessionHash: null,
      redactions: 0,
      notes: [],
    },
    {
      id: 'mr-7m6n5b4v3c',
      concept: 'order/shipping',
      conceptName: 'Order',
      modelId: null,
      api: 'mirakl',
      build: 'b-2026-11-12',
      canonicalField: 'shipping_method',
      kind: 'model-field-missing',
      status: 'routed',
      route: 'owner',
      reason: 'A canonical field proposal: every selected API has a shipping method.',
      problem: 'The Order model has no field for the shipping method, and all three APIs have one.',
      currentMapping: null,
      suggestion: null,
      validation: null,
      verified: null,
      reportCount: 1,
      noteCount: 0,
      createdAt: t(13),
      updatedAt: t(16),
      clientName: null,
      sessionHash: null,
      redactions: 0,
      notes: [],
    },
    {
      // a verified absence: the field is not available on this API, and what it must not be mapped from
      id: 'mr-8d7c6b5a4e',
      concept: 'inventory/stock',
      conceptName: 'Inventory',
      modelId: null,
      api: 'shopify',
      build: 'b-2026-11-14',
      canonicalField: 'low_stock_threshold',
      kind: 'wrong',
      status: 'open',
      route: null,
      reason: null,
      problem: 'low_stock_threshold is mapped on Shopify, but Shopify has no such field.',
      currentMapping: 'variants[].inventory_quantity',
      suggestion: {
        paths: [],
        fetch: null,
        notAvailable: true,
        notFrom: ['variants[].inventory_quantity'],
        evidence: [{ docId: 'endpoint:GET~/orders.json', quote: QUOTE, noQuote: null }],
      },
      validation: { ok: true, reason: null },
      verified: null,
      reportCount: 1,
      noteCount: 0,
      createdAt: t(19),
      updatedAt: t(19),
      clientName: 'claude-code 2.1',
      sessionHash: null,
      redactions: 0,
      notes: [],
    },
    {
      id: 'mr-2k3j4h5g6f',
      concept: 'inventory/stock',
      conceptName: 'Inventory',
      modelId: null,
      api: 'woocommerce',
      build: 'b-2026-11-14',
      canonicalField: 'manage_stock',
      kind: 'wrong',
      status: 'rejected',
      route: null,
      reason: 'The current mapping is right: manage_stock is the flag.',
      problem: 'manage_stock looks wrong to me.',
      currentMapping: 'manage_stock',
      suggestion: null,
      validation: null,
      verified: null,
      reportCount: 1,
      noteCount: 0,
      createdAt: t(11),
      updatedAt: t(12),
      clientName: 'cursor',
      sessionHash: null,
      redactions: 0,
      notes: [],
    },
  ];
}

const ORDER = (a: MappingReport, b: MappingReport) =>
  b.reportCount - a.reportCount || b.updatedAt.localeCompare(a.updatedAt);

export function listMappingReports(
  all: MappingReport[],
  q: { api: string | null; concept: string | null; status: string | null; kind: string | null },
): MappingReport[] {
  return all
    .filter(
      (r) =>
        (!q.api || r.api === q.api) &&
        (!q.concept || r.concept === q.concept) &&
        (!q.status || r.status === q.status) &&
        (!q.kind || r.kind === q.kind),
    )
    .map((r) => ({ ...r, notes: undefined }))
    .sort(ORDER);
}

/** The verified mappings of the mock server: the accepted reports that are in force. */
export function verifiedOf(all: MappingReport[]): VerifiedMapping[] {
  return all.flatMap((r) =>
    r.verified && r.suggestion
      ? [
          {
            id: r.verified.id,
            concept: r.concept,
            canonicalField: r.canonicalField,
            api: r.api,
            paths: r.suggestion.paths,
            fetch: r.suggestion.fetch ?? null,
            evidence: r.suggestion.evidence,
            build: r.verified.build ?? null,
            reportId: r.id,
            suspended: r.verified.suspended,
            suspendedReason: r.verified.suspendedReason ?? null,
            acceptedAt: r.updatedAt,
            validatedAt: r.verified.validatedAt ?? null,
          },
        ]
      : [],
  );
}
