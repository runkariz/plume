import type {
  ApiSummary,
  ApiRef,
  Concept,
  ModelSnapshot,
  SuggestQuery,
  SuggestResponse,
} from '@/api/types';
import realOrder40 from './fixtures/realOrder40.json';

/** Sample data from the mockups pics/plume-src/09..11. */
function candidate(
  id: string,
  name: string,
  category: string,
  summary: string,
  endpoints: number,
  models: number,
  guides: number,
  text: string,
  color: string,
): ApiSummary {
  return {
    id,
    name,
    category,
    summary,
    endpoints,
    models,
    guides,
    docsAsOf: '2026-11-14',
    status: { kind: 'ready', recallAt5: 0.92 },
    logo: { text, color },
  };
}

export const modelCandidates: ApiSummary[] = [
  candidate(
    'shopify',
    'Shopify Admin REST',
    'e-commerce',
    'Products, orders, customers, inventory and fulfillment for Shopify stores.',
    137,
    31,
    18,
    'S',
    '#5a8f2e',
  ),
  candidate(
    'woocommerce',
    'WooCommerce REST',
    'e-commerce',
    'Products, orders, customers, coupons, taxes and shipping for WordPress stores.',
    168,
    44,
    14,
    'W',
    '#7f54b3',
  ),
  candidate(
    'mirakl',
    'Mirakl Seller API',
    'e-commerce',
    'Offers, orders, shipments, products and messages for marketplace sellers.',
    96,
    38,
    11,
    'M',
    '#2a6edb',
  ),
  candidate(
    'bigcommerce',
    'BigCommerce Catalog',
    'e-commerce',
    'Catalog, pricing, inventory and channel listings for BigCommerce stores.',
    211,
    57,
    16,
    'B',
    '#34313f',
  ),
  candidate(
    'stripe',
    'Stripe API',
    'payments',
    'Payments, subscriptions, invoices, payouts and the events that tie them together.',
    412,
    96,
    41,
    'St',
    '#635bff',
  ),
  candidate(
    'github',
    'GitHub REST',
    'developer-tools',
    'Repositories, issues, pull requests, actions, checks and organization admin.',
    603,
    140,
    27,
    'G',
    '#24292f',
  ),
];

const REFS: Record<string, ApiRef> = {
  shopify: {
    id: 'shopify',
    name: 'Shopify Admin REST',
    shortName: 'Shopify',
    logo: { text: 'S', color: '#5a8f2e' },
  },
  woocommerce: {
    id: 'woocommerce',
    name: 'WooCommerce REST',
    shortName: 'WooCommerce',
    logo: { text: 'W', color: '#7f54b3' },
  },
  mirakl: {
    id: 'mirakl',
    name: 'Mirakl Seller API',
    shortName: 'Mirakl',
    logo: { text: 'M', color: '#2a6edb' },
  },
  bigcommerce: {
    id: 'bigcommerce',
    name: 'BigCommerce Catalog',
    shortName: 'BigCommerce',
    logo: { text: 'B', color: '#34313f' },
  },
  stripe: {
    id: 'stripe',
    name: 'Stripe API',
    shortName: 'Stripe',
    logo: { text: 'St', color: '#635bff' },
  },
  github: {
    id: 'github',
    name: 'GitHub REST',
    shortName: 'GitHub',
    logo: { text: 'G', color: '#24292f' },
  },
};

export function apiRef(id: string): ApiRef | undefined {
  return REFS[id];
}

type Cov = 'direct' | 'derived' | 'absent';
const MOCK_APIS = ['shopify', 'woocommerce', 'mirakl'] as const;
const nice = (id: string) => REFS[id]?.shortName ?? id;
const list = (items: string[]) =>
  items.length < 2
    ? items.join('')
    : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;

interface Spec {
  id: string;
  name: string;
  fields: number;
  cov: [Cov, Cov, Cov];
  ops: Concept['operations'];
  difficulty: Concept['difficulty'];
}
const OK = { tone: 'ok', label: 'Straightforward' } as const;
const WARN = { tone: 'warn', label: 'Joins needed' } as const;
const BAD = { tone: 'bad', label: 'Only in some' } as const;
const RW: Concept['operations'] = ['read', 'write'];
const R: Concept['operations'] = ['read'];

/** The mock catalogue: enough concepts to page through (36), several in only one API. */
const SPECS: Spec[] = [
  {
    id: 'product',
    name: 'Product',
    fields: 14,
    cov: ['direct', 'direct', 'direct'],
    ops: RW,
    difficulty: OK,
  },
  {
    id: 'order',
    name: 'Order',
    fields: 18,
    cov: ['direct', 'direct', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'inventory',
    name: 'Inventory',
    fields: 7,
    cov: ['derived', 'direct', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'shipment',
    name: 'Shipment',
    fields: 9,
    cov: ['direct', 'derived', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'customer',
    name: 'Customer',
    fields: 11,
    cov: ['direct', 'direct', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'location',
    name: 'Location',
    fields: 6,
    cov: ['direct', 'absent', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'refund',
    name: 'Refund',
    fields: 8,
    cov: ['direct', 'direct', 'derived'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'discount',
    name: 'Discount',
    fields: 10,
    cov: ['direct', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'return',
    name: 'Return',
    fields: 9,
    cov: ['derived', 'absent', 'direct'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'review',
    name: 'Review',
    fields: 7,
    cov: ['absent', 'direct', 'derived'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'category',
    name: 'Category',
    fields: 6,
    cov: ['direct', 'direct', 'direct'],
    ops: RW,
    difficulty: OK,
  },
  {
    id: 'tag',
    name: 'Tag',
    fields: 3,
    cov: ['direct', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'coupon',
    name: 'Coupon',
    fields: 9,
    cov: ['absent', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'invoice',
    name: 'Invoice',
    fields: 12,
    cov: ['absent', 'derived', 'direct'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'payment',
    name: 'Payment',
    fields: 10,
    cov: ['direct', 'direct', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'tax',
    name: 'Tax',
    fields: 5,
    cov: ['direct', 'direct', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'shipping-zone',
    name: 'Shipping zone',
    fields: 6,
    cov: ['direct', 'direct', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'warehouse',
    name: 'Warehouse',
    fields: 7,
    cov: ['derived', 'absent', 'direct'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'attribute',
    name: 'Attribute',
    fields: 8,
    cov: ['direct', 'direct', 'direct'],
    ops: RW,
    difficulty: OK,
  },
  {
    id: 'brand',
    name: 'Brand',
    fields: 4,
    cov: ['absent', 'direct', 'direct'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'collection',
    name: 'Collection',
    fields: 7,
    cov: ['direct', 'derived', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'cart',
    name: 'Cart',
    fields: 9,
    cov: ['direct', 'absent', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'subscription',
    name: 'Subscription',
    fields: 11,
    cov: ['direct', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'gift-card',
    name: 'Gift card',
    fields: 8,
    cov: ['direct', 'absent', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'supplier',
    name: 'Supplier',
    fields: 6,
    cov: ['absent', 'absent', 'direct'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'campaign',
    name: 'Campaign',
    fields: 7,
    cov: ['direct', 'absent', 'derived'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'page',
    name: 'Page',
    fields: 6,
    cov: ['direct', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'menu',
    name: 'Menu',
    fields: 5,
    cov: ['direct', 'absent', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'webhook',
    name: 'Webhook',
    fields: 6,
    cov: ['direct', 'direct', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'theme',
    name: 'Theme',
    fields: 5,
    cov: ['direct', 'absent', 'absent'],
    ops: R,
    difficulty: BAD,
  },
  {
    id: 'offer',
    name: 'Offer',
    fields: 13,
    cov: ['absent', 'absent', 'direct'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'promotion',
    name: 'Promotion',
    fields: 9,
    cov: ['direct', 'derived', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
  {
    id: 'currency',
    name: 'Currency',
    fields: 3,
    cov: ['direct', 'direct', 'direct'],
    ops: R,
    difficulty: OK,
  },
  {
    id: 'note',
    name: 'Note',
    fields: 3,
    cov: ['direct', 'absent', 'absent'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'message',
    name: 'Message',
    fields: 6,
    cov: ['absent', 'absent', 'direct'],
    ops: RW,
    difficulty: BAD,
  },
  {
    id: 'fulfillment',
    name: 'Fulfillment',
    fields: 10,
    cov: ['direct', 'derived', 'direct'],
    ops: RW,
    difficulty: WARN,
  },
];

/** A concept as the server sends it for the selected APIs (coverage of the others is absent). */
function build(spec: Spec, apiIds: string[]): Concept {
  const coverage: Record<string, Cov> = {};
  const apiCounts: NonNullable<Concept['apiCounts']> = {};
  apiIds.forEach((id) => {
    const i = MOCK_APIS.indexOf(id as (typeof MOCK_APIS)[number]);
    const cov: Cov = i === -1 ? 'absent' : (spec.cov[i] ?? 'absent');
    coverage[id] = cov;
    apiCounts[id] =
      cov === 'direct'
        ? {
            models: 1,
            endpoints: 2 + (spec.fields % 5),
            operations: spec.ops.includes('write') ? ['read', 'create', 'update'] : ['read'],
            fields: spec.fields * 2 + 3,
          }
        : { models: 0, endpoints: 0, operations: [], fields: 0 };
  });
  const direct = apiIds.filter((id) => coverage[id] === 'direct').map(nice);
  const derived = apiIds.filter((id) => coverage[id] === 'derived').map(nice);
  const reason =
    `${spec.name} is documented as a model in ${list(direct)}` +
    (derived.length
      ? `, and can be reconstructed from the endpoints of ${list(derived)}`
      : direct.length > 1
        ? ', with matching fields'
        : '') +
    `. About ${spec.fields} fields are likely to map.`;
  return {
    id: spec.id,
    name: spec.name,
    reason,
    apiCounts,
    likelyFields: spec.fields,
    coverage,
    operations: spec.ops,
    difficulty: spec.difficulty,
  };
}

const present = (c: Concept) => Object.values(c.coverage).filter((v) => v !== 'absent').length;

/** The mock of POST /v1/models/suggest: scope, search, require, chips and paging, as the server does them. */
export function sampleSuggestions(apiIds: string[], q: SuggestQuery = {}): SuggestResponse {
  const apis = apiIds.map((id) => REFS[id]).filter((a): a is ApiRef => Boolean(a));
  const all = SPECS.map((s) => build(s, apiIds));
  const text = (q.q ?? '').trim().toLowerCase();
  const matches = (c: Concept) =>
    (!text || `${c.name} ${c.id} ${c.reason}`.toLowerCase().includes(text)) &&
    (q.require ?? []).every((id) => (c.coverage[id] ?? 'absent') !== 'absent');
  const base = all.filter(matches);
  const multi = base.filter((c) => present(c) >= 2);
  const single = base.filter((c) => present(c) === 1);
  const inAll = (c: Concept) => present(c) === apiIds.length;
  const writes = (c: Concept) => c.operations.includes('write');
  const scope = q.only ?? 'multi';
  let rows = scope === 'single' ? single : scope === 'all' ? [...multi, ...single] : multi;
  if (q.inAll) rows = rows.filter(inAll);
  if (q.writeOnly) rows = rows.filter(writes);
  const limit = Math.min(q.limit ?? 24, 100);
  const offset = q.offset ?? 0;
  const page = rows.slice(offset, offset + limit);
  const singles = all.filter((c) => present(c) === 1);
  return {
    apis,
    concepts: page,
    total: rows.length,
    limit,
    offset,
    nextOffset: offset + limit < rows.length ? offset + limit : null,
    counts: {
      all: multi.length,
      inAll: multi.filter(inAll).length,
      write: multi.filter(writes).length,
      single: single.length,
    },
    notModeled: {
      count: singles.length,
      summary:
        'resources exist in only one of these APIs, such as theme assets and marketplace messages.',
    },
  };
}

const apiBuild = {
  shopify: '2026-11-14',
  woocommerce: '2026-11-14',
  mirakl: '2026-11-12',
} as const;

export const inventorySnapshot: ModelSnapshot = {
  // newer docs exist, none of the changes touches a field this model cites
  impact: { status: 'updated_unaffected', affectedCount: 0, breakingCount: 0 },
  id: 'snap_8f3a21',
  name: 'Inventory',
  description: 'Stock per SKU and location, stock management and backorder behavior.',
  status: 'generated_unverified',
  generatedAt: '2026-11-14T14:20:00Z',
  promptVersion: 'v1',
  inputs: (['shopify', 'woocommerce', 'mirakl'] as const).map((id) => ({
    ...(REFS[id] as ApiRef),
    build: apiBuild[id],
  })),
  operations: [
    {
      name: 'set absolute stock',
      kind: 'set',
      sources: {
        shopify: {
          endpoint: 'POST /admin/api/{version}/inventory_levels/set.json',
          fields: ['location_id', 'inventory_item_id', 'available'],
          semantics: 'absolute; omitted means 0',
          evidence: [
            {
              quote: 'Sets the inventory level for an inventory item at a location.',
              anchor: '',
              docId: 'endpoint:POST~/admin/api/{version}/inventory_levels/set.json',
            },
          ],
        },
        woocommerce: {
          endpoint: 'PUT /wp-json/wc/v3/products/{id}',
          fields: ['stock_quantity', 'manage_stock'],
          semantics: 'absolute',
          evidence: [],
        },
      },
    },
    {
      name: 'adjust stock by a delta',
      kind: 'adjust',
      sources: {
        shopify: {
          endpoint: 'POST /admin/api/{version}/inventory_levels/adjust.json',
          fields: ['available_adjustment'],
          semantics: 'delta',
          evidence: [],
        },
      },
    },
    {
      name: 'read stock',
      kind: 'read',
      sources: {
        shopify: {
          endpoint: 'GET /admin/api/{version}/inventory_levels.json',
          fields: ['available'],
          semantics: null,
          evidence: [],
        },
        mirakl: {
          endpoint: 'GET /api/offers',
          fields: ['quantity'],
          semantics: null,
          evidence: [],
        },
      },
    },
  ],
  fields: [
    {
      name: 'sku',
      type: 'string',
      required: true,
      support: { shopify: 'supported', woocommerce: 'supported', mirakl: 'supported' },
      sources: {
        shopify: {
          paths: [{ path: 'variants[].sku', type: 'string' }],
          // a kind with nothing more to say: a plain chip, nothing to open
          conversion: { kind: 'array-vs-single' },
        },
        woocommerce: { paths: [{ path: 'sku', type: 'string' }] },
        mirakl: { paths: [{ path: 'shop_sku', type: 'string' }] },
      },
    },
    {
      name: 'location_id',
      type: 'string',
      required: false,
      support: { shopify: 'supported', woocommerce: 'unsupported', mirakl: 'unsupported' },
      sources: {
        shopify: {
          paths: [{ path: 'inventory_levels[].location_id', type: 'integer' }],
          // no map: the systems are named in `format`
          conversion: { kind: 'code-system', format: 'Shopify location id -> warehouse code' },
        },
      },
    },
    {
      name: 'quantity_available',
      type: 'integer',
      required: true,
      support: { shopify: 'derived', woocommerce: 'supported', mirakl: 'supported' },
      sources: {
        shopify: {
          paths: [{ path: 'inventory_levels[].available', type: 'integer' }],
          conversion: {
            kind: 'split',
            note: 'One level per location; the canonical quantity is the sum over the locations the shop stocks.',
          },
          transform: 'join: inventory_item_id',
          fetch: {
            endpoint: 'GET /admin/api/2026-10/locations/{location_id}/inventory_levels.json',
          },
          join: ['variants[].inventory_item_id = inventory_levels[].inventory_item_id'],
          evidence: [
            {
              quote: 'Total available stock quantity across all locations.',
              anchor: 'variants[].inventory_quantity, products list, build 2026-11-14',
            },
          ],
        },
        woocommerce: { paths: [{ path: 'stock_quantity', type: 'integer' }] },
        mirakl: {
          paths: [{ path: 'quantity', type: 'integer' }],
          conversion: { kind: 'datetime', format: 'ISO 8601, UTC (2026-11-14T14:20:00Z)' },
        },
      },
    },
    {
      name: 'manage_stock',
      type: 'boolean',
      required: true,
      support: { shopify: 'derived', woocommerce: 'supported', mirakl: 'unsupported' },
      sources: {
        shopify: {
          paths: [{ path: 'variants[].inventory_management', type: 'string | null' }],
          transform: 'not null = true',
          evidence: [
            {
              quote: 'The fulfillment service tracking inventory; null means not tracked.',
              anchor: 'variants[].inventory_management, build 2026-11-14',
            },
          ],
        },
        woocommerce: {
          paths: [{ path: 'manage_stock', type: 'boolean' }],
          evidence: [
            {
              quote: '',
              anchor: 'manage_stock, build 2026-11-14',
              docId: 'endpoint:GET~/wp-json/wc/v3/products',
              noQuote: "the field's own description is only a label (Stock management)",
            },
          ],
        },
      },
    },
    {
      name: 'allow_backorder',
      type: 'boolean',
      required: false,
      support: { shopify: 'derived', woocommerce: 'derived', mirakl: 'unsupported' },
      sources: {
        shopify: {
          paths: [{ path: 'variants[].inventory_policy', type: 'string' }],
          conversion: {
            kind: 'enum',
            map: { continue: 'true', deny: 'false' },
            note: 'Shopify names the policy; the canonical field is a flag.',
          },
          transform: 'continue = true',
        },
        woocommerce: {
          paths: [{ path: 'backorders', type: 'string' }],
          conversion: {
            kind: 'enum',
            map: { no: 'false', notify: 'true', yes: 'true' },
            unmapped: ['preorder', 'on_request'],
          },
          transform: 'no = false; notify, yes = true',
        },
      },
    },
    {
      name: 'low_stock_threshold',
      type: 'integer',
      required: false,
      support: { shopify: 'unsupported', woocommerce: 'supported', mirakl: 'supported' },
      sources: {
        woocommerce: { paths: [{ path: 'low_stock_amount', type: 'integer' }] },
        mirakl: { paths: [{ path: 'min_quantity_alert', type: 'integer' }] },
      },
    },
    {
      name: 'lead_time_days',
      type: 'integer',
      required: false,
      support: { shopify: 'unsupported', woocommerce: 'unsupported', mirakl: 'supported' },
      sources: {
        mirakl: { paths: [{ path: 'leadtime_to_ship', type: 'integer' }] },
      },
    },
  ],
  openQuestions: [
    {
      question: 'Is the canonical quantity **available** or **on hand**?',
      detail: 'Shopify exposes available per location; WooCommerce has one number.',
    },
    { question: 'What is **location_id** when an API has no locations?' },
    { question: 'Backorders: a **boolean**, or keep the policy value?' },
  ],
  coverage: {
    shopify: { mapped: 5, total: 7 },
    woocommerce: { mapped: 5, total: 7 },
    mirakl: { mapped: 4, total: 7 },
  },
  citations: { checked: 14, found: 14, missing: [] },
};

export const productSnapshot: ModelSnapshot = {
  ...inventorySnapshot,
  // current: the pinned build is still latest (after the spread: Inventory's impact must not leak in)
  impact: { status: 'current', affectedCount: 0, breakingCount: 0 },
  id: 'snap_prod01',
  name: 'Product',
  description: 'Items for sale: title, SKU, price, status, variants and descriptions.',
  fields: [
    {
      name: 'title',
      type: 'string',
      required: true,
      support: { shopify: 'supported', woocommerce: 'supported', mirakl: 'supported' },
      sources: {
        shopify: { paths: [{ path: 'title', type: 'string' }] },
        woocommerce: { paths: [{ path: 'name', type: 'string' }] },
        mirakl: { paths: [{ path: 'product_title', type: 'string' }] },
      },
    },
    {
      name: 'sku',
      type: 'string',
      required: true,
      support: { shopify: 'supported', woocommerce: 'supported', mirakl: 'supported' },
      sources: {
        shopify: { paths: [{ path: 'variants[].sku', type: 'string' }] },
        woocommerce: { paths: [{ path: 'sku', type: 'string' }] },
        mirakl: { paths: [{ path: 'shop_sku', type: 'string' }] },
      },
    },
  ],
  openQuestions: [],
  coverage: {
    shopify: { mapped: 2, total: 2 },
    woocommerce: { mapped: 2, total: 2 },
    mirakl: { mapped: 2, total: 2 },
  },
  citations: { checked: 6, found: 5, missing: ['product_title'] },
};

/** A real 40-field Order model (Shopify + WooCommerce + Mirakl), copied from a live snapshot: the shape of a big model. */
export const order40Snapshot: ModelSnapshot = {
  ...(realOrder40 as unknown as ModelSnapshot),
  // the docs of two of its APIs changed after it was built (the shape plume-6f's server sends)
  stale: true,
  // and a visible change touches two of its mappings, one of them breaking
  impact: { status: 'affected', affectedCount: 2, breakingCount: 1 },
  staleInputs: [
    {
      api: 'shopify',
      pinned: 'b-e9f58eb5a9cb0b835a4ed625c692e546',
      current: 'b-91c706474d71676ed99042893780964e',
    },
    {
      api: 'woocommerce',
      pinned: 'b-574fe7333dffe19c2d28cda69505f8f6',
      current: 'b-49e2f7af69657435ac9b19f491ea1f7e',
    },
  ],
};

export const snapshots: Record<string, ModelSnapshot> = {
  [order40Snapshot.id]: order40Snapshot,
  [inventorySnapshot.id]: inventorySnapshot,
  [productSnapshot.id]: productSnapshot,
};

/** A model with nested fields as the server sends them: canonical `path` on every field, `fields` on containers. */
const leaf = (
  name: string,
  path: string,
  support: Record<string, 'supported' | 'derived' | 'unsupported'>,
  sources: Record<string, string>,
  extra: Partial<ModelSnapshot['fields'][number]> = {},
): ModelSnapshot['fields'][number] => ({
  name,
  path,
  type: 'string',
  required: false,
  support,
  sources: Object.fromEntries(
    Object.entries(sources).map(([api, p]) => [
      api,
      {
        paths: [{ path: p, type: 'string' }],
        evidence: [{ quote: `${name} as documented`, anchor: '', docId: `model:${api}-order` }],
      },
    ]),
  ),
  ...extra,
});

export const nestedSnapshot: ModelSnapshot = {
  // a personal model pinned to a build that has no notes: nobody can say whether it is affected
  impact: { status: 'unknown', affectedCount: 0, breakingCount: 0 },
  id: 'u-nested0000000000000000000000001',
  name: 'Order with lines',
  description: 'An order with its customer and its lines.',
  status: 'generated_unverified',
  generatedAt: '2026-11-16T09:00:00Z',
  promptVersion: 'v1',
  inputs: (['shopify', 'woocommerce'] as const).map((id) => ({
    ...(REFS[id] as ApiRef),
    build: apiBuild[id],
  })),
  fields: [
    leaf(
      'id',
      'id',
      { shopify: 'supported', woocommerce: 'supported' },
      { shopify: 'id', woocommerce: 'id' },
      {
        required: true,
      },
    ),
    {
      // a container without sources of its own: derived because its children are mapped
      name: 'customer',
      path: 'customer',
      type: 'object',
      required: false,
      support: { shopify: 'derived', woocommerce: 'derived' },
      sources: {},
      fields: [
        leaf(
          'name',
          'customer.name',
          { shopify: 'supported', woocommerce: 'supported' },
          {
            shopify: 'customer.first_name',
            woocommerce: 'billing.first_name',
          },
        ),
        leaf(
          'email',
          'customer.email',
          { shopify: 'supported', woocommerce: 'unsupported' },
          {
            shopify: 'customer.email',
          },
        ),
      ],
    },
    {
      // a container that is also mapped as a whole (it has sources of its own)
      name: 'lines',
      path: 'lines',
      type: 'array',
      required: false,
      support: { shopify: 'supported', woocommerce: 'supported' },
      sources: {
        shopify: { paths: [{ path: 'line_items', type: 'array' }] },
        woocommerce: { paths: [{ path: 'line_items', type: 'array' }] },
      },
      fields: [
        leaf(
          'sku',
          'lines[].sku',
          { shopify: 'supported', woocommerce: 'supported' },
          {
            shopify: 'line_items[].sku',
            woocommerce: 'line_items[].sku',
          },
        ),
        {
          name: 'price',
          path: 'lines[].price',
          type: 'object',
          required: false,
          support: { shopify: 'derived', woocommerce: 'derived' },
          sources: {},
          fields: [
            leaf(
              'amount',
              'lines[].price.amount',
              { shopify: 'derived', woocommerce: 'supported' },
              {
                shopify: 'line_items[].price',
                woocommerce: 'line_items[].price',
              },
            ),
            leaf(
              'currency',
              'lines[].price.currency',
              { shopify: 'unsupported', woocommerce: 'unsupported' },
              {},
            ),
          ],
        },
      ],
    },
  ],
  openQuestions: [],
  coverage: { shopify: { mapped: 5, total: 6 }, woocommerce: { mapped: 4, total: 6 } },
  citations: { checked: 8, found: 8, missing: [] },
};
