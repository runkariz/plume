import type { ApiSummary } from '@/api/types';

/** Sample data copied from the mockup pics/plume-src/01-home.html. */
export const sampleApis: ApiSummary[] = [
  api(
    'shopify',
    'Shopify Admin REST',
    'E-commerce',
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
    'Payments',
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
    'Developer tools',
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
    'Communication',
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
    'Communication',
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
    'Productivity',
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
  ...(sampleApis[0] as (typeof sampleApis)[number]),
  name: 'Shopify Admin REST API',
  chunks: 409,
  isLive: true,
  tag: 'latest',
  quality: {
    recallAt5: 0.94,
    mrr: 0.81,
    inventedEndpoints: 0,
    goldQuestions: 40,
    evaluatedAt: '2026-11-14',
  },
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

export function detailFor(id: string): ApiDetail | undefined {
  if (id === 'shopify') return shopifyDetail;
  const base = sampleApis.find((a) => a.id === id);
  if (!base) return undefined;
  return {
    ...shopifyDetail,
    ...base,
    chunks: base.endpoints + base.models + base.guides * 4,
    isLive: base.status.kind === 'ready',
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

export function sampleCheck(method: string, path: string, params: string[]): CheckCallResponse {
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
  };
}
