import type {
  ApiRef,
  RelatedCandidate,
  RelatedConcept,
  RelatedConcepts,
  RelatedEvidence,
  RelationSupport,
} from '@/api/types';
import { apiRef } from './modelData';

const ev = (
  kind: RelationSupport,
  quote: string,
  paths: string[],
  fetch: string | null = null,
): RelatedEvidence => ({
  kind,
  quote,
  paths,
  fetch,
  docId: `model:${paths[0] ?? 'doc'}`,
  many: true,
});

function candidate(
  parent: string,
  child: string,
  sources: RelatedCandidate['sources'],
  options: RelatedCandidate['options'],
): RelatedCandidate {
  return {
    id: `${parent.toLowerCase()}>${child.toLowerCase()}`,
    parent: { id: parent.toLowerCase(), name: parent },
    child: { id: child.toLowerCase(), name: child },
    options,
    sources,
  };
}

const embedded = { kind: 'embedded', cardinality: '1:n' } as const;
const reference = { kind: 'reference', cardinality: 'n:1' } as const;

/** What the mock knows is connected to what (Product, Order); every other concept has nothing related. */
function relatedList(): Record<string, RelatedConcept[]> {
  return {
    product: [
      {
        id: 'variant',
        name: 'Variant',
        kinds: { shopify: ['nested', 'sub_resource', 'id_field'] },
        candidates: [
          candidate(
            'Product',
            'Variant',
            {
              shopify: [
                ev('nested', 'The variants of the product.', ['products[].variants[]']),
                ev(
                  'sub_resource',
                  'Retrieves a list of product variants.',
                  ['/products/{product_id}/variants'],
                  'GET /admin/api/{version}/products/{product_id}/variants.json',
                ),
                ev('id_field', 'The unique numeric identifier for the parent product.', [
                  'products[].variants[].product_id',
                ]),
              ],
            },
            [embedded, reference],
          ),
        ],
      },
      {
        id: 'variation',
        name: 'Variation',
        kinds: { woocommerce: ['sub_resource'] },
        candidates: [
          candidate(
            'Product',
            'Variation',
            {
              woocommerce: [
                ev(
                  'sub_resource',
                  'List all product variations.',
                  ['/products/{product_id}/variations'],
                  'GET /wp-json/wc/{version}/products/{product_id}/variations',
                ),
              ],
            },
            [reference],
          ),
        ],
      },
      {
        id: 'image',
        name: 'Image',
        kinds: { shopify: ['nested'], woocommerce: ['nested'] },
        candidates: [
          candidate(
            'Product',
            'Image',
            {
              shopify: [ev('nested', 'A list of product image objects.', ['products[].images[]'])],
              woocommerce: [ev('nested', 'List of images.', ['images[]'])],
            },
            [embedded],
          ),
        ],
      },
      {
        id: 'lineitem',
        name: 'LineItem',
        kinds: { shopify: ['id_field'] },
        candidates: [
          candidate(
            'Product',
            'LineItem',
            {
              shopify: [
                ev('id_field', 'The ID of the product that the line item belongs to.', [
                  'orders[].line_items[].product_id',
                ]),
              ],
            },
            [reference],
          ),
        ],
      },
    ],
    order: [
      {
        id: 'lineitem',
        name: 'LineItem',
        kinds: { shopify: ['nested'], woocommerce: ['nested'] },
        candidates: [
          candidate(
            'Order',
            'LineItem',
            {
              shopify: [ev('nested', 'A list of line item objects.', ['orders[].line_items[]'])],
              woocommerce: [ev('nested', 'Line items data.', ['line_items[]'])],
            },
            [embedded],
          ),
        ],
      },
      {
        id: 'refund',
        name: 'Refund',
        kinds: { woocommerce: ['sub_resource', 'id_field'] },
        candidates: [
          candidate(
            'Order',
            'Refund',
            {
              woocommerce: [
                ev('sub_resource', 'List all refunds of an order.', ['/orders/{order_id}/refunds']),
                ev('id_field', 'The order the refund belongs to.', ['refunds[].parent_id']),
              ],
            },
            [reference],
          ),
        ],
      },
    ],
  };
}

const NAMES: Record<string, string> = { product: 'Product', order: 'Order' };

/** POST /v1/models/suggest-related, for the mock server. */
export function relatedFor(
  apis: string[],
  concept: string,
  limit = 24,
  offset = 0,
): RelatedConcepts {
  const key = concept.toLowerCase();
  const all = relatedList()[key] ?? [];
  // a related concept only counts when one of the chosen APIs documents it
  const here = all.filter((r) => apis.some((a) => (r.kinds[a] ?? []).length > 0));
  const page = here.slice(offset, offset + limit);
  const refs: ApiRef[] = apis.flatMap((a) => {
    const r = apiRef(a);
    return r ? [{ ...r, build: `b-${a}` }] : [];
  });
  const variant = here.find((r) => r.id === 'variant');
  const variation = here.find((r) => r.id === 'variation');
  const aliases: RelatedConcepts['aliases'] =
    key === 'product' && variant && variation
      ? [
          {
            parent: { id: 'product', name: 'Product' },
            names: {
              shopify: { id: 'variant', name: 'Variant' },
              woocommerce: { id: 'variation', name: 'Variation' },
            },
            evidence: {
              shopify: ev(
                'sub_resource',
                'Retrieves a list of product variants.',
                ['/products/{product_id}/variants'],
                'GET /admin/api/{version}/products/{product_id}/variants.json',
              ),
              woocommerce: ev(
                'sub_resource',
                'List all product variations.',
                ['/products/{product_id}/variations'],
                'GET /wp-json/wc/{version}/products/{product_id}/variations',
              ),
            },
            note: 'Different names at the same documented position. The docs do not say they are the same thing: offer it to the user; never merge on your own.',
          },
        ]
      : [];
  return {
    apis: refs,
    concept: { id: key, name: NAMES[key] ?? concept },
    related: page,
    total: here.length,
    limit,
    offset,
    nextOffset: offset + page.length < here.length ? offset + page.length : null,
    aliases: apis.includes('shopify') && apis.includes('woocommerce') ? aliases : [],
  };
}
