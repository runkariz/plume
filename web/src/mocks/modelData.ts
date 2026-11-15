import type { ApiSummary, ApiRef, Concept, ModelSnapshot, SuggestResponse } from '@/api/types';

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
    'E-commerce',
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
    'E-commerce',
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
    'E-commerce',
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
    'E-commerce',
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
    'Payments',
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
    'Developer tools',
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
function concept(
  id: string,
  name: string,
  description: string,
  likelyFields: number,
  cov: [Cov, Cov, Cov],
  operations: Concept['operations'],
  difficulty: Concept['difficulty'],
): Concept {
  return {
    id,
    name,
    description,
    likelyFields,
    coverage: { shopify: cov[0], woocommerce: cov[1], mirakl: cov[2] },
    operations,
    difficulty,
  };
}

const RW: Concept['operations'] = ['read', 'write'];

export function sampleSuggestions(apiIds: string[]): SuggestResponse {
  const apis = apiIds.map((id) => REFS[id]).filter((a): a is ApiRef => Boolean(a));
  const all: Concept[] = [
    concept(
      'product',
      'Product',
      'Items for sale: title, SKU, price, status, variants and descriptions.',
      14,
      ['direct', 'direct', 'direct'],
      RW,
      { tone: 'ok', label: 'Clean' },
    ),
    concept(
      'order',
      'Order',
      'Customer purchases with line items, totals, payment and fulfillment state.',
      18,
      ['direct', 'direct', 'direct'],
      RW,
      { tone: 'warn', label: 'Joins needed' },
    ),
    concept(
      'inventory',
      'Inventory',
      'Stock per SKU and location, stock management and backorder behavior.',
      7,
      ['derived', 'direct', 'direct'],
      RW,
      { tone: 'warn', label: 'Derived in 2' },
    ),
    concept(
      'shipment',
      'Shipment',
      'Packages sent for an order, with carrier, tracking and status.',
      9,
      ['direct', 'derived', 'direct'],
      RW,
      { tone: 'warn', label: 'Derived in 1' },
    ),
    concept(
      'customer',
      'Customer',
      'Buyer profiles with contact details and addresses.',
      11,
      ['direct', 'direct', 'absent'],
      ['read'],
      { tone: 'bad', label: 'Not in all 3' },
    ),
    concept(
      'location',
      'Location',
      'Warehouses and stores where stock is held.',
      6,
      ['direct', 'absent', 'absent'],
      ['read'],
      { tone: 'bad', label: 'Only in 1' },
    ),
  ];
  const concepts = all.map((c) => ({
    ...c,
    coverage: Object.fromEntries(apiIds.map((id) => [id, c.coverage[id] ?? ('absent' as const)])),
  }));
  return {
    apis,
    concepts,
    notModeled: {
      count: 9,
      summary: 'resources exist in only one API, such as marketplace messages and theme assets.',
    },
  };
}

const apiBuild = {
  shopify: '2026-11-14',
  woocommerce: '2026-11-14',
  mirakl: '2026-11-12',
} as const;

export const inventorySnapshot: ModelSnapshot = {
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
  fields: [
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
    {
      name: 'location_id',
      type: 'string',
      required: false,
      support: { shopify: 'supported', woocommerce: 'unsupported', mirakl: 'unsupported' },
      sources: {
        shopify: { paths: [{ path: 'inventory_levels[].location_id', type: 'integer' }] },
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
        mirakl: { paths: [{ path: 'quantity', type: 'integer' }] },
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
        woocommerce: { paths: [{ path: 'manage_stock', type: 'boolean' }] },
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
          transform: 'continue = true',
        },
        woocommerce: {
          paths: [{ path: 'backorders', type: 'string' }],
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

export const snapshots: Record<string, ModelSnapshot> = {
  [inventorySnapshot.id]: inventorySnapshot,
  [productSnapshot.id]: productSnapshot,
};
