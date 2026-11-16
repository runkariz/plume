import type {
  ChangeItem,
  ReleaseCounts,
  ReleaseDecision,
  ReleaseNotes,
  ReleaseReview,
  ReleaseSummary,
  ReportGroup,
  ReportPage,
  RollbackResult,
} from '@/api/types';

/**
 * Release notes in the mock server: per API a few builds (oldest first), each with the notes the server computed
 * against its base. The state machine follows the design: nothing is held after a publish; the maintainer KEEPS a
 * build or ROLLS BACK the tagged one (`latest` moves to its base; keep on a rolled-back build rolls forward while
 * `latest` is still its base). Promote makes a suspect/unknown item confirmed if the quote is plausible.
 */
export interface MockBuild {
  id: string;
  docsAsOf: string;
  createdAt: string;
  /** The build `latest` pointed to before this one was loaded (none for the first). */
  from: string | null;
  hasNotes: boolean;
  review: ReleaseReview;
  needsAttention: boolean;
  attentionReason: string | null;
  computedAt: string;
  decisions: ReleaseDecision[];
  items: ChangeItem[];
  package: { from: Pkg; to: Pkg } | null;
  gold: { before: Record<string, number>; after: Record<string, number> } | null;
}
type Pkg = { streamVersion: string; rulesHash: string; extractedAt: string };

export interface MockApiBuilds {
  builds: MockBuild[];
  /** The build `latest` points to. */
  latest: string;
}

export const REVIEW_SHOPIFY_NEW = 'b-shopify-20261114';
export const REVIEW_SHOPIFY_OLD = 'b-shopify-20261020';
export const REVIEW_SHOPIFY_FIRST = 'b-shopify-20260915';
export const REVIEW_WOO = 'b-woo-20261110';

const item = (
  id: string,
  over: Partial<ChangeItem> & Pick<ChangeItem, 'kind' | 'op' | 'class' | 'subject'>,
): ChangeItem => ({
  breaking: false,
  from: REVIEW_SHOPIFY_OLD,
  to: REVIEW_SHOPIFY_NEW,
  ...over,
  id,
});

const orderField = (name: string, cls: ChangeItem['class'], rule?: string): ChangeItem =>
  item(`ch-order-${name}`, {
    kind: 'response_field',
    op: 'removed',
    class: cls,
    breaking: true,
    breakingReason: 'field removed',
    subject: {
      docId: 'endpoint:GET~/admin/api/latest/orders.json',
      method: 'GET',
      path: '/admin/api/latest/orders.json',
      fieldPath: name,
      location: 'response',
    },
    before: {
      type: 'string',
      required: false,
      quote: `${name}: the ${name.replace(/_/g, ' ')} of the order.`,
    },
    after: null,
    evidence: {
      sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/order',
      anchor: 'order-property-' + name,
      pageHashBefore: 'sha256:9c1f0a77e2',
      pageHashAfter: 'sha256:9c1f0a77e2', // the page did not change: the extraction did
    },
    artifactRules: rule ? [rule] : [],
  });

function shopifyNotes(): MockBuild {
  const items: ChangeItem[] = [
    // confirmed and likely: what users will see
    item('ch-orders-note-attributes', {
      kind: 'response_field',
      op: 'added',
      class: 'confirmed',
      subject: {
        docId: 'endpoint:GET~/admin/api/latest/orders.json',
        method: 'GET',
        path: '/admin/api/latest/orders.json',
        fieldPath: 'note_attributes[].name',
        location: 'response',
      },
      before: null,
      after: { type: 'string', required: false, quote: 'The name of the note attribute.' },
      evidence: {
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/order',
        anchor: 'order-property-note-attributes',
        pageHashBefore: 'sha256:11aa22bb33',
        pageHashAfter: 'sha256:44cc55dd66',
      },
    }),
    item('ch-orders-fulfillment-status', {
      kind: 'param',
      op: 'removed',
      class: 'confirmed',
      breaking: true,
      breakingReason: 'query parameter removed',
      subject: {
        docId: 'endpoint:GET~/admin/api/latest/orders.json',
        method: 'GET',
        path: '/admin/api/latest/orders.json',
        fieldPath: 'fulfillment_status',
        location: 'query',
      },
      before: {
        type: 'string',
        required: false,
        quote: 'Filter orders by their fulfillment status.',
      },
      after: null,
      evidence: {
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/order',
        anchor: 'get-orders',
        pageHashBefore: 'sha256:11aa22bb33',
        pageHashAfter: 'sha256:44cc55dd66',
      },
    }),
    item('ch-webhook-tax-lines', {
      kind: 'webhook_event',
      op: 'type',
      class: 'likely',
      breaking: true,
      breakingReason: 'type changed string -> number',
      subject: {
        docId: 'trigger:orders/create',
        fieldPath: 'tax_lines[].rate',
        location: 'response',
      },
      before: { type: 'string' },
      after: { type: 'number' },
      evidence: {
        changelog: "Shopify changelog: 'tax_lines rate is a number'",
        sourceUrl: 'https://shopify.dev/changelog',
      },
    }),
    item('ch-wording', {
      kind: 'response_field',
      op: 'description',
      class: 'confirmed',
      wordingOnly: true,
      subject: { docId: 'model:order', model: 'Order', fieldPath: 'note', location: 'response' },
      before: { quote: 'A note.' },
      after: { quote: 'A note about the order, set by the merchant.' },
      evidence: {
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/order',
        anchor: 'order-property-note',
      },
    }),
    // suspect: the extraction, not the docs
    orderField('shipping_lines', 'suspect', 'A2-alphabetical-cutoff'),
    orderField('subtotal_price', 'suspect', 'A2-alphabetical-cutoff'),
    orderField('total_price', 'suspect', 'A2-alphabetical-cutoff'),
    item('ch-variant-barcode', {
      kind: 'property',
      op: 'removed',
      class: 'suspect',
      breaking: true,
      breakingReason: 'property removed',
      subject: {
        docId: 'model:productvariant',
        model: 'ProductVariant',
        fieldPath: 'barcode',
        location: 'response',
      },
      before: { type: 'string', quote: 'The barcode, UPC or ISBN number for the product.' },
      after: null,
      evidence: {
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/product-variant',
        pageHashBefore: 'sha256:aa11',
        pageHashAfter: 'sha256:aa11',
      },
      artifactRules: ['A3-property-count-drop'],
    }),
    item('ch-variant-sku', {
      kind: 'property',
      op: 'removed',
      class: 'suspect',
      breaking: true,
      breakingReason: 'property removed',
      subject: {
        docId: 'model:productvariant',
        model: 'ProductVariant',
        fieldPath: 'sku',
        location: 'response',
      },
      before: { type: 'string', quote: 'A unique identifier for the product variant in the shop.' },
      after: null,
      evidence: {
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/product-variant',
        pageHashBefore: 'sha256:aa11',
        pageHashAfter: 'sha256:aa11',
      },
      artifactRules: ['A3-property-count-drop'],
    }),
    // unknown: no source evidence either way
    item('ch-auth-scope', {
      kind: 'scope',
      op: 'removed',
      class: 'unknown',
      breaking: true,
      breakingReason: 'scope removed',
      subject: { docId: 'auth:oauth', fieldPath: 'read_marketing_events' },
      before: { quote: 'Access to marketing events.' },
      after: null,
      evidence: null,
    }),
  ];
  return {
    id: REVIEW_SHOPIFY_NEW,
    docsAsOf: '2026-11-14',
    createdAt: '2026-11-14T09:00:00Z',
    from: REVIEW_SHOPIFY_OLD,
    hasNotes: true,
    review: 'pending',
    needsAttention: true,
    attentionReason:
      '3 suspect removed fields of Order look like an alphabetical cut-off, and gold recall dropped 0.03',
    computedAt: '2026-11-14T09:05:00Z',
    decisions: [],
    items,
    package: {
      from: {
        streamVersion: '1.4.2',
        rulesHash: 'rules-7f3a',
        extractedAt: '2026-10-20T08:00:00Z',
      },
      to: { streamVersion: '1.4.3', rulesHash: 'rules-9b21', extractedAt: '2026-11-14T08:30:00Z' },
    },
    gold: { before: { 'recall@5': 0.94, mrr: 0.88 }, after: { 'recall@5': 0.91, mrr: 0.87 } },
  };
}

export function seedReleases(): Record<string, MockApiBuilds> {
  const first: MockBuild = {
    id: REVIEW_SHOPIFY_FIRST,
    docsAsOf: '2026-09-15',
    createdAt: '2026-09-15T09:00:00Z',
    from: null,
    hasNotes: false, // the first build has no base: no notes
    review: 'kept',
    needsAttention: false,
    attentionReason: null,
    computedAt: '2026-09-15T09:05:00Z',
    decisions: [],
    items: [],
    package: null,
    gold: null,
  };
  const old: MockBuild = {
    id: REVIEW_SHOPIFY_OLD,
    docsAsOf: '2026-10-20',
    createdAt: '2026-10-20T09:00:00Z',
    from: REVIEW_SHOPIFY_FIRST,
    hasNotes: true,
    review: 'kept',
    needsAttention: false,
    attentionReason: null,
    computedAt: '2026-10-20T09:05:00Z',
    decisions: [
      { by: 'maintainer', at: '2026-10-20T10:00:00Z', decision: 'keep', note: 'Looks right.' },
    ],
    items: [
      item('ch-old-1', {
        kind: 'endpoint',
        op: 'added',
        class: 'confirmed',
        from: REVIEW_SHOPIFY_FIRST,
        to: REVIEW_SHOPIFY_OLD,
        subject: {
          docId: 'endpoint:GET~/admin/api/latest/gift_cards.json',
          method: 'GET',
          path: '/admin/api/latest/gift_cards.json',
        },
        evidence: {
          sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/gift-card',
        },
      }),
    ],
    package: {
      from: {
        streamVersion: '1.4.2',
        rulesHash: 'rules-7f3a',
        extractedAt: '2026-09-15T08:00:00Z',
      },
      to: { streamVersion: '1.4.2', rulesHash: 'rules-7f3a', extractedAt: '2026-10-20T08:00:00Z' },
    },
    gold: { before: { 'recall@5': 0.94, mrr: 0.88 }, after: { 'recall@5': 0.94, mrr: 0.88 } },
  };
  const woo: MockBuild = {
    id: REVIEW_WOO,
    docsAsOf: '2026-11-10',
    createdAt: '2026-11-10T09:00:00Z',
    from: null,
    hasNotes: false,
    review: 'kept',
    needsAttention: false,
    attentionReason: null,
    computedAt: '2026-11-10T09:05:00Z',
    decisions: [],
    items: [],
    package: null,
    gold: null,
  };
  return {
    shopify: { builds: [first, old, shopifyNotes()], latest: REVIEW_SHOPIFY_NEW },
    woocommerce: { builds: [woo], latest: REVIEW_WOO },
  };
}

// ---- views ----

const visible = (i: ChangeItem) => i.class === 'confirmed' || i.class === 'likely';

export function countsOf(b: MockBuild): ReleaseCounts {
  const v = b.items.filter(visible);
  return {
    confirmed: v.filter((i) => i.class === 'confirmed').length,
    likely: v.filter((i) => i.class === 'likely').length,
    breaking: v.filter((i) => i.breaking).length,
    suspect: b.items.filter((i) => i.class === 'suspect').length,
    unknown: b.items.filter((i) => i.class === 'unknown').length,
    wordingOnly: v.filter((i) => i.wordingOnly).length,
    renamed: 0,
    total: b.items.length,
  };
}

export function timelineJson(api: MockApiBuilds): ReleaseSummary[] {
  return [...api.builds]
    .filter((b) => b.hasNotes && b.from)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map((b) => ({
      from: b.from as string,
      to: b.id,
      toDocsAsOf: b.docsAsOf,
      computedAt: b.computedAt,
      review: b.review,
      needsAttention: b.needsAttention,
      attentionReason: b.attentionReason,
      tagged: api.latest === b.id,
      counts: countsOf(b),
    }));
}

const RULES: Record<string, { title: string; explanation: string }> = {
  'A1-mass-removal': {
    title: 'Mass removal',
    explanation:
      'More than 30% of a document’s fields were removed while its source page did not change.',
  },
  'A2-alphabetical-cutoff': {
    title: 'Alphabetical cut-off',
    explanation:
      'The removed fields of the document are exactly the ones after a letter in alphabetical order: the extraction stopped early, the docs did not change.',
  },
  'A3-property-count-drop': {
    title: 'Property count drop',
    explanation:
      'A model lost more than 30% of its properties while its source page did not change.',
  },
  unknown: {
    title: 'No source evidence',
    explanation:
      'Plume has no page text to check these against, so it cannot say whether the docs or the extraction changed.',
  },
};

export function reportOf(b: MockBuild): ReportGroup[] {
  const hidden = b.items.filter((i) => !visible(i));
  const byRule = new Map<string, ChangeItem[]>();
  for (const i of hidden) {
    const rule = i.class === 'unknown' ? 'unknown' : (i.artifactRules?.[0] ?? 'unknown');
    byRule.set(rule, [...(byRule.get(rule) ?? []), i]);
  }
  // as the server does: each group carries its `count` and only the first 50 items (the rest through reportPage)
  return [...byRule.entries()].map(([rule, items]) => ({
    rule,
    title: RULES[rule]?.title ?? rule,
    explanation: RULES[rule]?.explanation ?? '',
    count: items.length,
    items: items.slice(0, 50),
  }));
}

/** GET .../report/{rule}?cursor&limit: one group, paged. */
export function reportPage(
  b: MockBuild,
  rule: string,
  cursor: number,
  limit: number,
): ReportPage | null {
  const all = b.items
    .filter((i) => !visible(i))
    .filter(
      (i) => (i.class === 'unknown' ? 'unknown' : (i.artifactRules?.[0] ?? 'unknown')) === rule,
    );
  if (all.length === 0) return null;
  const next = cursor + limit;
  return {
    rule,
    count: all.length,
    items: all.slice(cursor, next),
    nextCursor: next < all.length ? next : null,
  };
}

export function notesJson(api: MockApiBuilds, b: MockBuild, apiId = 'shopify'): ReleaseNotes {
  return {
    review: b.review,
    needsAttention: b.needsAttention,
    attentionReason: b.attentionReason,
    tagged: api.latest === b.id,
    computedAt: b.computedAt,
    decisions: b.decisions,
    counts: countsOf(b),
    report: reportOf(b),
    // EVERY item: the visible ones carry `visibleToUsers`, the suspect and unknown ones do not
    items: b.items.map((i) => ({
      ...i,
      visibleToUsers: visible(i),
      computedClass: COMPUTED.get(`${b.id}/${i.id}`) ?? i.class,
    })),
    from: b.from,
    api: apiId,
    to: b.id,
    toDocsAsOf: b.docsAsOf,
    extractorChanged: Boolean(b.package) && b.package?.from.rulesHash !== b.package?.to.rulesHash,
    package: b.package,
    gold: b.gold,
  };
}

// ---- decisions (the server's rules) ----

export type Failure = { status: number; error: string; message: string };
const invalid = (message: string): Failure => ({ status: 409, error: 'invalid_state', message });

export function keep(
  api: MockApiBuilds,
  b: MockBuild,
  note: string | undefined,
  by = 'maintainer',
): Failure | null {
  const at = '2026-11-16T12:00:00Z';
  if (b.review === 'rolled_back') {
    // rolling forward: only while `latest` is still its base
    if (api.latest !== b.from)
      return invalid(
        'latest moved on since this build was rolled back: it cannot be rolled forward',
      );
    api.latest = b.id;
    b.review = 'kept';
    b.decisions.push({ by, at, decision: 'rollforward', note: note ?? null });
    return null;
  }
  if (b.review === 'kept') return invalid('this build is already kept');
  b.review = 'kept';
  b.decisions.push({ by, at, decision: 'keep', note: note ?? null });
  return null;
}

export function rollback(
  api: MockApiBuilds,
  b: MockBuild,
  reason: string,
  by = 'maintainer',
): Failure | RollbackResult {
  if (!b.from) return invalid('this is the first build: there is nothing to roll back to');
  if (api.latest !== b.id) return invalid('only the build that is `latest` can be rolled back');
  if (b.review === 'rolled_back') return invalid('this build is already rolled back');
  api.latest = b.from;
  b.review = 'rolled_back';
  b.decisions.push({ by, at: '2026-11-16T12:05:00Z', decision: 'rollback', reason });
  return { tag: 'latest', buildId: b.from, previous: b.id, review: 'rolled_back' };
}

export function promote(
  b: MockBuild,
  itemId: string,
  quote: string,
  by = 'maintainer',
): Failure | ChangeItem {
  const it = b.items.find((i) => i.id === itemId);
  if (!it) return { status: 404, error: 'not_found', message: 'No such change' };
  if (it.class === 'confirmed' || it.class === 'likely')
    return invalid('this change is already visible to users');
  // the server verifies the quote against the source text of this build; the mock accepts a quote that names the field
  const field = (it.subject.fieldPath ?? '').replace(/\[\]/g, '');
  const ok =
    quote.trim().length >= 12 &&
    field !== '' &&
    quote.toLowerCase().includes(field.toLowerCase().split('.').pop() ?? '');
  if (!ok)
    return {
      status: 422,
      error: 'QUOTE_NOT_VERIFIED',
      message: 'That quote is not in the source text of this build.',
    };
  COMPUTED.set(`${b.id}/${it.id}`, it.class); // so a demote can restore the computed class
  it.class = 'confirmed';
  it.promotedBy = by;
  it.promotedAt = '2026-11-16T12:10:00Z';
  b.decisions.push({ by, at: it.promotedAt, decision: 'promote', item: it.id, note: quote });
  return it;
}

/** The class an item had before it was promoted by hand. */
const COMPUTED = new Map<string, ChangeItem['class']>();
export function demote(b: MockBuild, itemId: string, by = 'maintainer'): Failure | ChangeItem {
  const it = b.items.find((i) => i.id === itemId);
  if (!it) return { status: 404, error: 'not_found', message: 'No such change' };
  if (!it.promotedBy) return invalid('this change was not promoted by hand');
  it.class = COMPUTED.get(`${b.id}/${it.id}`) ?? 'unknown';
  it.promotedBy = null;
  it.promotedAt = null;
  b.decisions.push({ by, at: '2026-11-16T12:15:00Z', decision: 'demote', item: it.id });
  return it;
}

/** The copy-issues text for stream, built on the server (one string for the clipboard and the download). */
export function issuesText(api: string, b: MockBuild, format: 'markdown' | 'text'): string {
  const md = format === 'markdown';
  const h1 = (s: string) => (md ? `# ${s}` : s.toUpperCase());
  const h2 = (s: string) => (md ? `## ${s}` : `\n${s}`);
  const code = (s: string) => (md ? `\`${s}\`` : s);
  const lines = [
    h1(`Extraction issues: ${api}, build ${b.id}`),
    '',
    `Base build: ${b.from ?? 'none'}`,
    `stream ${b.package?.from.streamVersion ?? '?'} -> ${b.package?.to.streamVersion ?? '?'}, rules ${b.package?.from.rulesHash ?? '?'} -> ${b.package?.to.rulesHash ?? '?'}`,
  ];
  for (const g of reportOf(b)) {
    lines.push('', h2(`${g.rule}: ${g.title} (${g.items.length})`), g.explanation);
    for (const i of g.items) {
      lines.push(
        `- ${code(`${i.subject.method ?? ''} ${i.subject.path ?? i.subject.model ?? i.subject.docId ?? ''}`.trim())} ${i.op} ${code(i.subject.fieldPath ?? '')}` +
          ` | A: ${i.before?.type ?? i.before?.quote ?? '-'} | B: ${i.after?.type ?? i.after?.quote ?? '-'}` +
          ` | ${i.evidence?.sourceUrl ?? 'no source url'} | page ${i.evidence?.pageHashBefore ?? '?'} -> ${i.evidence?.pageHashAfter ?? '?'}`,
      );
    }
  }
  return lines.join('\n');
}
