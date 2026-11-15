import type {
  AuthList,
  AuthSchemeDetail,
  EnvironmentsOut,
  TriggerDetail,
  TriggerList,
  McpOut,
  TriggerSummary,
} from '@/api/types';

/** Shaped like the real package-sections API (docs/openapi.json on develop): auth, triggers, environments, icon. */

const BUILD = 'b-6ff6063a275d40c14e4bcdd001f1c9ae';

/** Which sample APIs have which sections: Shopify has everything, Stripe an API key only, the rest nothing. */
export const sectionCounts: Record<
  string,
  { auth: number; triggers: number; webhookEndpoints: number }
> = {
  shopify: { auth: 1, triggers: 3, webhookEndpoints: 0 },
  stripe: { auth: 1, triggers: 0, webhookEndpoints: 0 },
};
export const noSections = { auth: 0, triggers: 0, webhookEndpoints: 0 };

export const iconApis = new Set(['shopify']);

/** A tiny valid PNG (a 2x2 purple square) used as the sample package icon. */
export const ICON_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR4nGNkYGD4z8DAwMDEQCUAAC8wARHfTVo8AAAAAElFTkSuQmCC';

const SHOPIFY_SCOPES = [
  ['read_analytics', 'View store metrics'],
  ['read_assigned_fulfillment_orders', 'View or manage fulfillment orders'],
  ['write_assigned_fulfillment_orders', 'View or manage fulfillment orders'],
  ['read_customers', 'View or manage customers'],
  ['write_customers', 'View or manage customers'],
  ['read_orders', 'View or manage orders'],
  ['write_orders', 'View or manage orders'],
  ['read_products', 'View or manage products'],
  ['write_products', 'View or manage products'],
  ['read_inventory', 'View or manage inventory'],
  ['write_inventory', 'View or manage inventory'],
  ['read_locations', 'View locations'],
  ['read_shipping', 'View shipping'],
  ['write_shipping', 'Manage shipping'],
  ['read_themes', 'View themes'],
] as const;

export function authFor(api: string): AuthList {
  if (api === 'shopify')
    return {
      api,
      build: BUILD,
      present: true,
      note: null,
      schemes: [
        {
          id: 'oauth2-authorization-code',
          docId: 'auth:oauth2-authorization-code',
          name: 'OAuth2 authorization code',
          type: 'OAUTH2',
          grantType: 'authorization_code',
          headerName: 'X-Shopify-Access-Token',
          queryParam: null,
          scopes: SHOPIFY_SCOPES.length,
          variables: 0,
        },
      ],
    };
  if (api === 'stripe')
    return {
      api,
      build: BUILD,
      present: true,
      note: null,
      schemes: [
        {
          id: 'api-key',
          docId: 'auth:api-key',
          name: 'API key (secret key)',
          type: 'API_KEY',
          grantType: null,
          headerName: 'Authorization',
          queryParam: null,
          scopes: 0,
          variables: 1,
        },
      ],
    };
  return { api, build: BUILD, present: false, note: 'not in this package', schemes: [] };
}

export function authDetailFor(api: string, id: string): AuthSchemeDetail | undefined {
  const summary = authFor(api).schemes.find((s) => s.id === id);
  if (!summary) return undefined;
  const base = {
    api,
    build: BUILD,
    id: summary.id,
    docId: summary.docId,
    name: summary.name,
    type: summary.type,
    grantType: summary.grantType,
    headerName: summary.headerName,
    queryParam: summary.queryParam,
    testUrl: null as string | null,
    file: `${id}.json`,
  };
  if (api === 'shopify')
    return {
      ...base,
      scopes: SHOPIFY_SCOPES.map(([scope, description]) => ({ scope, description })),
      variables: [],
      setupSteps: [
        {
          order: 1,
          text: "Redirect the merchant to Shopify's authorization page to approve requested access scopes.",
        },
        { order: 2, text: 'Validate the callback query parameters sent to your redirect URI.' },
        { order: 3, text: 'Exchange the authorization code for an access token.' },
      ],
      tokenLifetime: {
        notes:
          'Expiring offline access tokens come with a refresh_token used to obtain a new access token.',
        refreshBehavior: 'refresh-token',
      },
      scheme: {
        authorizationType: 'OAUTH2',
        grantType: 'authorization_code',
        scopes: SHOPIFY_SCOPES.length,
      },
      variablesSchema: null,
    };
  return {
    ...base,
    testUrl: 'https://api.stripe.com/v1/balance',
    scopes: [],
    variables: [
      { name: 'api_key', description: 'Your secret API key', type: 'string', required: true },
    ],
    setupSteps: null,
    tokenLifetime: null,
    scheme: { authorizationType: 'API_KEY', header: 'Authorization' },
    variablesSchema: {
      type: 'object',
      required: ['api_key'],
      properties: { api_key: { type: 'string', description: 'Your secret API key' } },
    },
  };
}

const SHOPIFY_EVENTS: TriggerSummary[] = [
  {
    key: 'app/scopes_update',
    docId: 'trigger:app-scopes_update',
    title: 'app/scopes_update',
    description:
      'Occurs whenever the access scopes of any installation are modified. Allows apps to keep track of the granted access scopes of their installations.',
    resource: 'shop',
    delivery: 'webhook',
  },
  {
    key: 'app/uninstalled',
    docId: 'trigger:app-uninstalled',
    title: 'app/uninstalled',
    description: null,
    resource: null,
    delivery: 'webhook',
  },
  {
    key: 'orders/create',
    docId: 'trigger:orders-create',
    title: 'orders/create',
    description: 'Occurs whenever a new order is created.',
    resource: 'orders',
    delivery: 'webhook',
  },
];

/** The webhook delivery mechanism of the Shopify package, as the real API sends it (verbatim shape). */
export const SHOPIFY_WEBHOOK_MECHANISM: Record<string, unknown> = {
  id: 'post-admin-api-latest-webhooks-json-2026-10',
  mode: 'api',
  handshake: { kind: 'none' },
  list: { endpointId: 'get-admin-api-latest-webhooks-json' },
  subscribe: {
    endpointId: 'post-admin-api-latest-webhooks-json-2026-10',
    callbackUrl: { in: 'body', pointer: '/webhook/address' },
    events: { in: 'body', pointer: '/webhook/topic', shape: 'array' },
  },
  unsubscribe: {
    idVar: 'webhook_id',
    endpointId: 'delete-admin-api-latest-webhooks-webhook-id-json-2026-10',
  },
  eventsAvailable: ['app/scopes_update', 'app/uninstalled', 'orders/create', 'orders/updated'],
  provenance: {
    source: 'docs',
    evidence: ['Create a new webhook subscription by specifying both an address and a topic.'],
    evidenceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/webhook',
  },
};

export function triggersFor(api: string, limit = 50, offset = 0): TriggerList {
  if (api !== 'shopify')
    return {
      api,
      build: BUILD,
      present: false,
      note: 'not in this package',
      total: 0,
      items: [],
      webhooks: [],
    };
  return {
    api,
    build: BUILD,
    present: true,
    note: null,
    total: SHOPIFY_EVENTS.length,
    items: SHOPIFY_EVENTS.slice(offset, offset + limit),
    webhooks: [SHOPIFY_WEBHOOK_MECHANISM],
  };
}

/** Only the "stripe" sample pretends to have an MCP server (real docs-only packages never do). */
export function mcpFor(api: string): McpOut {
  if (api !== 'stripe')
    return { api, build: BUILD, present: false, note: 'not in this package', servers: [] };
  return {
    api,
    build: BUILD,
    present: true,
    note: null,
    servers: [
      {
        id: 'stripe-mcp',
        server: { name: 'Stripe MCP', url: 'https://mcp.stripe.example/mcp' },
        tools: [
          {
            tool: 'list_customers',
            inputSchema: { type: 'object', properties: { limit: { type: 'integer' } } },
            outputSchema: null,
          },
          {
            tool: 'create_invoice',
            inputSchema: { type: 'object', required: ['customer'] },
            outputSchema: { type: 'object' },
          },
        ],
      },
    ],
  };
}

export function triggerDetailFor(api: string, key: string): TriggerDetail | undefined {
  if (api !== 'shopify') return undefined;
  const t = SHOPIFY_EVENTS.find((e) => e.key === key || e.docId === key);
  if (!t) return undefined;
  return {
    ...t,
    api,
    build: BUILD,
    sourceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/webhook',
    event: {
      key: t.key,
      title: t.title,
      delivery: t.delivery,
      resource: t.resource,
      description: t.description,
      provenance: {
        source: 'docs',
        evidenceUrl: 'https://shopify.dev/docs/api/admin-rest/latest/resources/webhook',
      },
    },
  };
}

export function environmentsFor(api: string): EnvironmentsOut {
  if (api === 'shopify')
    return {
      api,
      build: BUILD,
      present: true,
      note: null,
      environments: [
        {
          key: 'production',
          kind: 'production',
          name: 'production',
          baseUrl: 'https://{{app_env.vars.host}}',
          servers: { api: 'https://{{app_env.vars.host}}' },
          isDefault: true,
        },
      ],
      versioning: { format: 'date', scheme: 'path', current: '2026-10', versions: ['2026-10'] },
      baseUrls: ['https://{{app_env.vars.host}}'],
      variablesSchema: null,
    };
  return {
    api,
    build: BUILD,
    present: false,
    note: 'not in this package',
    environments: [],
    versioning: null,
    baseUrls: null,
    variablesSchema: null,
  };
}
