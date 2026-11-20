import type { ApiSummary } from '@/api/types';

/** Sample data copied from the mockup pics/plume-src/01-home.html. */
const baseApis: ApiSummary[] = [
  api(
    'shopify',
    'Shopify Admin REST',
    'e-commerce',
    'Products, orders, customers, inventory and fulfillment for Shopify stores.',
    137,
    31,
    18,
    '2026-11-14',
    { kind: 'ready', recallAt5: 0.94 },
    'S',
    '#5a8f2e',
  ),
  api(
    'stripe',
    'Stripe API',
    'payments',
    'Payments, subscriptions, invoices, payouts and the events that tie them together.',
    412,
    96,
    41,
    '2026-11-12',
    { kind: 'ready', recallAt5: 0.91 },
    'St',
    '#635bff',
  ),
  api(
    'github',
    'GitHub REST',
    'developer-tools',
    'Repositories, issues, pull requests, actions, checks and organization admin.',
    603,
    140,
    27,
    '2026-11-09',
    { kind: 'ready', recallAt5: 0.89 },
    'G',
    '#24292f',
  ),
  api(
    'twilio',
    'Twilio Messaging',
    'communication',
    'Send and receive SMS, MMS and WhatsApp messages, with status callbacks.',
    74,
    18,
    12,
    '2026-11-03',
    { kind: 'ready', recallAt5: 0.92 },
    'T',
    '#f22f46',
  ),
  api(
    'slack',
    'Slack Web API',
    'communication',
    'Channels, messages, users, files and workflows for Slack workspaces.',
    218,
    52,
    20,
    '2026-10-28',
    { kind: 'ready', recallAt5: 0.88 },
    'Sl',
    '#4a154b',
  ),
  api(
    'notion',
    'Notion API',
    'productivity',
    'Pages, databases, blocks and users, with the search and comments endpoints.',
    46,
    22,
    9,
    '2026-11-14',
    { kind: 'updating', progress: 0.62 },
    'N',
    '#37352f',
  ),
];

/** Shopify's package has an icon (served by the API); the other sample APIs fall back to the letter tile. */
export const sampleApis: ApiSummary[] = baseApis.map((a) =>
  a.id === 'shopify' ? { ...a, logo: { ...a.logo, url: '/v1/apis/shopify/icon' } } : a,
);

function api(
  id: string,
  name: string,
  category: string,
  summary: string,
  endpoints: number,
  models: number,
  guides: number,
  docsAsOf: string,
  status: ApiSummary['status'],
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
    docsAsOf,
    status,
    logo: { text, color },
  };
}

import { noSections, sectionCounts } from './sectionData';
import type {
  ApiDetail,
  AskResponse,
  BrowseItem,
  CheckCallResponse,
  SearchHit,
  TraceStep,
} from '@/api/types';

const SHOPIFY_BASE = '/admin/api/latest';

/** Sample data from the mockup pics/plume-src/02-api-detail.html. */
export const shopifyDetail: ApiDetail = {
  rateLimits: [
    {
      scope: 'app',
      group: 'rest-admin',
      limit: 40,
      windowSeconds: 20,
      algorithm: 'leaky-bucket',
      headerNames: ['X-Shopify-Shop-Api-Call-Limit'],
      notes: 'Sample numbers of the mock backend.',
    },
  ],
  ...(sampleApis[0] as (typeof sampleApis)[number]),
  name: 'Shopify Admin REST API',
  chunks: 409,
  isLive: true,
  tag: 'latest',
  tags: ['latest'],
  versions: ['2026-11-14'],
  docLink: 'https://shopify.dev/docs/api/admin-rest',
  sources: [
    {
      url: 'https://shopify.dev/docs/api/admin-rest',
      kind: 'docs',
      fetchedAt: '2026-11-14T08:00:00Z',
    },
    {
      url: 'https://shopify.dev/openapi/admin-rest.json',
      kind: 'spec',
      fetchedAt: '2026-11-14T08:05:00Z',
    },
    { url: 'https://shopify.dev/changelog', kind: 'changelog', fetchedAt: '2026-11-14T08:10:00Z' },
  ],
  extractedAt: '2026-11-14T08:30:00Z',
  quality: {
    recallAt5: 0.94,
    mrr: 0.81,
    inventedEndpoints: 0,
    goldQuestions: 40,
    evaluatedAt: '2026-11-14',
    top1Rate: 0.97,
    factAccuracy: 1,
    missingExpected: 0,
    gatePassed: true,
    bySource: [
      { source: 'docs', recallAt5: 0.96, mrr: 0.84, top1Rate: 0.98, questions: 26 },
      { source: 'spec', recallAt5: 0.91, mrr: 0.76, top1Rate: 0.93, questions: 14 },
    ],
  },
  packageWarnings: [
    {
      code: 'default-environment-by-order',
      text: 'default-environment-by-order: 2 environments, none marked default',
    },
    { code: 'knowledge-links', text: 'knowledge-links: 3 units with endpointId' },
    {
      code: 'unknown-endpoint',
      text: 'unknown-endpoint: knowledge unit pagination names an endpoint that is not in the package',
    },
    { code: 'icon-missing', text: 'icon-missing: no connector/icon.* in the package' },
    {
      code: 'partial-model',
      text: 'partial-model: 4 models are marked incomplete (x-complete false)',
    },
  ],
  index: {
    embedding: 'gemini-embedding-001',
    dimensions: 768,
    store: 'Postgres + pgvector',
    build: '2026-11-14',
  },
  connect: {
    claudeCode: 'claude mcp add --transport http plume \\\n  https://plume.example/mcp',
  },
};

/** The Amazon SP-API vendor package as plume-l2 has it: 13 OpenAPI specs, the docs page, a changelog linked twice. */
const AMAZON_SPECS = [
  ['vendor-orders-api-model', 'vendorOrders.json'],
  [
    'vendor-direct-fulfillment-shipping-api-model',
    'vendorDirectFulfillmentShipping_2021-12-28.json',
  ],
  ['vendor-direct-fulfillment-orders-api-model', 'vendorDirectFulfillmentOrders_2021-12-28.json'],
  ['vendor-direct-fulfillment-inventory-api-model', 'vendorDirectFulfillmentInventory_v1.json'],
  [
    'vendor-direct-fulfillment-payments-api-model',
    'vendorDirectFulfillmentPayments_2021-12-28.json',
  ],
  [
    'vendor-direct-fulfillment-sandbox-test-data-api-model',
    'vendorDirectFulfillmentSandboxData_2021-10-28.json',
  ],
  [
    'vendor-direct-fulfillment-transactions-api-model',
    'vendorDirectFulfillmentTransactions_2021-12-28.json',
  ],
  ['vendor-invoices-api-model', 'vendorInvoices.json'],
  ['vendor-shipments-api-model', 'vendorShipments.json'],
  ['vendor-transaction-status-api-model', 'vendorTransactionStatus.json'],
  ['vendor-direct-fulfillment-shipping-api-model', 'vendorDirectFulfillmentShipping_v1.json'],
  ['vendor-direct-fulfillment-orders-api-model', 'vendorDirectFulfillmentOrders_v1.json'],
  ['vendor-direct-fulfillment-payments-api-model', 'vendorDirectFulfillmentPayments_v1.json'],
] as const;

export const amazonVendorDetail: ApiDetail = {
  ...shopifyDetail,
  id: 'amazon-sp-vendor',
  name: 'Amazon SP-API (Vendor)',
  docLink: 'https://developer-docs.amazon.com/sp-api/docs',
  sources: [
    {
      url: 'https://developer-docs.amazon.com/sp-api/docs',
      kind: 'docs',
      fetchedAt: '2026-11-16T08:00:00Z',
    },
    ...AMAZON_SPECS.map(([dir, file]) => ({
      url: `https://raw.githubusercontent.com/amzn/selling-partner-api-models/main/models/${dir}/${file}`,
      kind: 'spec',
      fetchedAt: '2026-11-16T08:05:00Z',
    })),
    {
      url: 'https://developer-docs.amazon.com/sp-api/changelog',
      kind: 'changelog',
      fetchedAt: '2026-11-16T08:10:00Z',
    },
    // the same page on a host alias
    {
      url: 'https://developer-docs.amazon/sp-api/changelog',
      kind: 'changelog',
      fetchedAt: '2026-11-16T08:10:00Z',
    },
  ],
  extractedAt: '2026-11-16T08:30:00Z',
  // the package describes the algorithm and the headers but no numbers (as Amazon's does today)
  rateLimits: [
    {
      scope: 'endpoint-group',
      algorithm: 'leaky-bucket',
      headerNames: ['x-amzn-RateLimit-Limit'],
      notes: 'Each operation has its own rate and burst.',
    },
  ],
};

export function detailFor(id: string): ApiDetail | undefined {
  if (id === 'amazon-sp-vendor') return amazonVendorDetail;
  if (id === 'shopify')
    return {
      ...shopifyDetail,
      sections: sectionCounts.shopify,
      logo: { ...shopifyDetail.logo, url: '/v1/apis/shopify/icon' },
    };
  const base = sampleApis.find((a) => a.id === id);
  if (!base) return undefined;
  return {
    ...shopifyDetail,
    ...base,
    chunks: base.endpoints + base.models + base.guides * 4,
    isLive: base.status.kind === 'ready',
    sections: sectionCounts[id] ?? noSections,
    logo: { ...base.logo, url: null },
    // one source (the manifest's docs url), as a package without a sources list has
    sources: [{ url: `https://docs.example.com/${id}`, kind: 'docs', fetchedAt: null }],
    extractedAt: '2026-11-14T08:30:00Z',
    rateLimits: [],
  };
}

function ep(
  slug: string,
  method: BrowseItem['method'],
  path: string,
  title: string,
  resource: string,
): BrowseItem {
  return {
    id: `endpoint:${slug}`,
    kind: 'endpoint',
    title,
    method,
    path: `${SHOPIFY_BASE}${path}`,
    resource,
  };
}

export const shopifyItems: BrowseItem[] = [
  ep('get-orders', 'GET', '/orders.json', 'Retrieve a list of orders', 'orders'),
  ep('create-order', 'POST', '/orders.json', 'Create an order', 'orders'),
  ep('get-order', 'GET', '/orders/{order_id}.json', 'Retrieve a specific order', 'orders'),
  ep('update-order', 'PUT', '/orders/{order_id}.json', 'Update an order', 'orders'),
  ep('delete-order', 'DELETE', '/orders/{order_id}.json', 'Delete an order', 'orders'),
  ep('get-products', 'GET', '/products.json', 'Retrieve a list of products', 'products'),
  ep('create-product', 'POST', '/products.json', 'Create a new product', 'products'),
  ep(
    'get-customer',
    'GET',
    '/customers/{customer_id}.json',
    'Retrieve a single customer',
    'customers',
  ),
  ep('count-orders', 'GET', '/orders/count.json', 'Retrieve an order count', 'orders'),
  {
    id: 'model:order',
    kind: 'model',
    title: 'Order',
    resource: 'orders',
  },
  {
    id: 'model:product',
    kind: 'model',
    title: 'Product',
    resource: 'products',
  },
  {
    id: 'guide:pagination',
    kind: 'guide',
    title: 'Pagination: Link header, URL lifespan and range searches',
    resource: 'shared',
  },
  {
    id: 'guide:rate-limits',
    kind: 'guide',
    title: 'REST Admin API request rate limits',
    resource: 'rate limits',
  },
];

/** Totals shown by the UI come from the API summary, not from the sample list length. */
export const shopifyKindTotals = { endpoint: 137, model: 31, guide: 18 } as const;

/** Sample data from the mockup pics/plume-src/08-try-it.html. */
export const sampleHits: SearchHit[] = [
  {
    id: 'guide:pagination',
    kind: 'guide',
    title: 'Pagination: Link header, URL lifespan and range searches',
    subtitle: 'guide · shared',
    snippet:
      'Cursor-based pagination: use the page_info value from the Link header, and pass only limit with it.',
    denseRank: 1,
    textRank: 2,
    denseScore: 0.92,
    textScore: 0.7,
    fused: 0.0325,
  },
  {
    id: 'endpoint:get-orders',
    kind: 'endpoint',
    title: 'Retrieve a list of orders',
    subtitle: `GET ${SHOPIFY_BASE}/orders.json`,
    snippet: 'Parameters: limit (max 250), page_info, status, created_at_min, fields.',
    denseRank: 3,
    textRank: 1,
    denseScore: 0.55,
    textScore: 0.92,
    fused: 0.0323,
  },
  {
    id: 'guide:rate-limits',
    kind: 'guide',
    title: 'REST Admin API request rate limits',
    subtitle: 'guide · rate limits',
    snippet: 'Leaky bucket: 40 requests per app per store, refilling at 2 per second.',
    denseRank: 2,
    textRank: 6,
    denseScore: 0.74,
    textScore: 0.28,
    fused: 0.031,
  },
  {
    id: 'endpoint:count-orders',
    kind: 'endpoint',
    title: 'Retrieve an order count',
    subtitle: `GET ${SHOPIFY_BASE}/orders/count.json`,
    snippet: 'Returns a count of orders matching the query parameters.',
    denseRank: 5,
    textRank: 4,
    denseScore: 0.4,
    textScore: 0.5,
    fused: 0.0307,
  },
];

export const sampleTrace: TraceStep[] = [
  { source: 'gemini', label: 'Embedded the question, 768 dims', ms: 38 },
  { source: 'postgres', label: 'Dense search with api_id = shopify', ms: 5 },
  { source: 'postgres', label: 'Full-text search', ms: 3 },
  { source: 'plume', label: 'Rank fusion, 8 results', ms: 1 },
];

export const sampleClaudePayload = `{
  "api": "shopify",
  "docs_as_of": "2026-11-14",
  "results": [
    { "id": "guide:pagination",
      "kind": "guide", "score": 0.0325 },
    { "id": "endpoint:get-orders",
      "method": "GET",
      "path": "/orders.json" }
  ]
}`;

export function sampleAsk(question: string): AskResponse {
  return {
    api: 'shopify',
    docsAsOf: '2026-11-14',
    question,
    passages: [
      {
        id: 'guide:pagination',
        title: 'Pagination: Link header, URL lifespan and range searches',
        quote:
          'Cursor-based pagination: use the page_info value from the Link header, and pass only limit with it.',
        sourceUrl: 'https://shopify.dev/docs/api/usage/pagination-rest',
      },
      {
        id: 'endpoint:get-orders',
        title: 'Retrieve a list of orders',
        quote: 'Parameters: limit (max 250), page_info, status, created_at_min, fields.',
        sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/order',
      },
    ],
    trace: sampleTrace,
    totalMs: 47,
  };
}

/** Operations that share POST /sync in the mock (RPC by name, like AliExpress): the `method` value picks one. */
const SYNC_OPERATIONS = [
  'aliexpress.affiliate.category.get',
  'aliexpress.affiliate.product.query',
  'ae.merchant.plan.list',
];

export function sampleCheck(method: string, path: string, params: string[]): CheckCallResponse {
  if (method === 'POST' && path === '/sync') {
    const given = params.find((p) => p.startsWith('method='))?.slice('method='.length);
    const base = {
      api: 'shopify',
      build: '2026-11-14',
      complete: true,
      checked: { endpoints: 137, models: 31 },
    };
    if (given && SYNC_OPERATIONS.includes(given))
      return {
        ...base,
        verdict: 'documented',
        matched: {
          id: `endpoint:POST~/sync@post-${given.replace(/\./g, '-')}`,
          method: 'POST',
          path: '/sync',
        },
        paramChecks: params
          .filter((p) => !p.startsWith('method='))
          .map((name) => ({ name, found: false, where: null })),
      };
    if (given)
      return {
        ...base,
        verdict: 'not_documented',
        matched: null,
        paramChecks: [],
        note: `no operation at POST /sync has method=${given}`,
      };
    return {
      ...base,
      verdict: 'ambiguous',
      matched: null,
      paramChecks: params.map((name) => ({ name, found: false, where: null })),
      alternatives: SYNC_OPERATIONS.map((o) => `endpoint:POST~/sync@post-${o.replace(/\./g, '-')}`),
      pick: {
        param: 'method',
        options: [...SYNC_OPERATIONS].sort().map((o) => ({
          value: o,
          docId: `endpoint:POST~/sync@post-${o.replace(/\./g, '-')}`,
        })),
      },
      note: `ambiguous: 156 operations share POST /sync; pass method=<name> in params or query (e.g. ${SYNC_OPERATIONS.map((o) => `method=${o}`).join(', ')})`,
    };
  }
  const found = shopifyItems.find(
    (i) => i.kind === 'endpoint' && i.method === method && i.path === path,
  );
  const known = new Set(['limit', 'page_info', 'status', 'created_at_min', 'fields']);
  return {
    api: 'shopify',
    build: '2026-11-14',
    verdict: found ? 'documented' : 'not_documented',
    complete: true,
    matched:
      found && found.method && found.path
        ? { id: found.id, method: found.method, path: found.path }
        : null,
    paramChecks: params.map((name) => ({
      name,
      found: Boolean(found) && known.has(name),
      where: found && known.has(name) ? 'query' : null,
    })),
    checked: { endpoints: 137, models: 31 },
    // why a path that matches a template is not documented (another version of the same operation)
    ...(!found && /\/orders/.test(path)
      ? { note: 'The documented operation is GET /admin/api/latest/orders.json.' }
      : {}),
  };
}
