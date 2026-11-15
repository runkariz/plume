import type {
  ModelLineage,
  ModelSet,
  ModelVisibility,
  RelationEdit,
  RelationOption,
  SetListItem,
  SetMember,
  SetRelation,
} from '@/api/types';
import { apiRef } from './modelData';

/** What the mock server keeps for a model set: the JSON plus who may see it and where it belongs. */
export interface StoredSet {
  set: ModelSet;
  lineageId: string;
  ownerKey?: string;
  createdAt: string;
}

const inputs = (ids: string[]): ModelSet['inputs'] =>
  ids.flatMap((id) => {
    const ref = apiRef(id);
    return ref ? [{ ...ref, build: `b-${id}` }] : [];
  });

const member = (concept: string, fieldCount: number, cov: Record<string, number>): SetMember => ({
  concept,
  modelId: `m-${concept.toLowerCase()}`,
  name: concept,
  fieldCount,
  coverage: Object.fromEntries(
    Object.entries(cov).map(([api, mapped]) => [api, { mapped, total: fieldCount }]),
  ),
  visibility: 'official',
  version: 1,
});

const opt = (
  kind: RelationOption['kind'],
  from: string,
  to: string,
  cardinality: RelationOption['cardinality'],
  fields: { embed?: string; ref?: [string, string] },
  editable: boolean,
  current: boolean,
  missing: string[] = [],
): RelationOption => ({
  kind,
  from,
  to,
  cardinality,
  embed: fields.embed ? { field: fields.embed } : null,
  ref: fields.ref ? { field: fields.ref[0], key: fields.ref[1] } : null,
  editable,
  missing,
  current,
});

export const SET_OFFICIAL = 'set_shop00000000000000000';
export const SET_UNRELEASED = 'set_draft0000000000000000';
export const SET_UNLISTED = 'u-set0000000000000000000001';
export const SET_OWNER_KEY = 'pk_set_demo_owner_key';

function orderItems(confirmed: boolean, current: 'embedded' | 'reference'): SetRelation {
  return {
    id: 'order-items',
    from: 'Order',
    to: 'Product',
    kind: current,
    cardinality: current === 'embedded' ? '1:n' : 'n:1',
    embed: current === 'embedded' ? { field: 'items' } : null,
    ref: current === 'reference' ? { field: 'order_id', key: 'id' } : null,
    confirmed,
    candidate: true,
    support: { shopify: 'nested', woocommerce: 'nested' },
    sources: {
      shopify: {
        as: 'nested',
        paths: ['line_items[].product_id'],
        evidence: [
          {
            docId: 'endpoint:GET~/admin/api/{version}/orders.json',
            quote: 'An array of line items, each with a product_id.',
            anchor: '',
          },
        ],
      },
      woocommerce: {
        as: 'nested',
        paths: ['line_items[].product_id'],
        evidence: [{ docId: 'model:order', quote: 'Line items of the order.' }],
      },
    },
    editableOptions: [
      opt('embedded', 'Order', 'Product', '1:n', { embed: 'items' }, true, current === 'embedded'),
      opt('embedded', 'Order', 'Product', '1:1', { embed: 'items' }, false, false, [
        'Order.items is an array: it cannot hold one Product',
      ]),
      opt(
        'reference',
        'Product',
        'Order',
        'n:1',
        { ref: ['order_id', 'id'] },
        false,
        current === 'reference',
        ['Product: a field holding the Order id'],
      ),
    ],
  };
}

function productVariants(confirmed: boolean): SetRelation {
  return {
    id: 'product-variants',
    from: 'Product',
    to: 'Variant',
    kind: 'embedded',
    cardinality: '1:n',
    embed: { field: 'variants' },
    ref: null,
    confirmed,
    candidate: true,
    // only Shopify documents it (nested); WooCommerce does not: with Shopify unchecked it is greyed out
    support: { shopify: 'nested', woocommerce: null },
    sources: {
      shopify: {
        as: 'nested',
        paths: ['variants[]'],
        evidence: [{ quote: 'The variants of the product.' }],
      },
    },
    editableOptions: [
      opt('embedded', 'Product', 'Variant', '1:n', { embed: 'variants' }, true, true),
      opt('reference', 'Variant', 'Product', 'n:1', { ref: ['product_id', 'id'] }, true, false),
    ],
  };
}

function build(
  id: string,
  name: string,
  visibility: ModelVisibility,
  relations: SetRelation[],
  extra: Partial<ModelSet> = {},
): ModelSet {
  return {
    kind: 'model_set',
    id,
    name,
    description: 'Products with their variants, and the orders that contain them.',
    visibility,
    official: visibility === 'official',
    origin: visibility === 'unlisted' ? 'user' : 'maintainer',
    generator: 'claude',
    generatedAt: '2026-11-16T10:00:00Z',
    releasedAt: visibility === 'official' ? '2026-11-16T11:00:00Z' : null,
    basedOn: null,
    inputs: inputs(['shopify', 'woocommerce']),
    stale: false,
    members: [
      member('Order', 12, { shopify: 9, woocommerce: 11 }),
      member('Product', 14, { shopify: 14, woocommerce: 13 }),
      member('Variant', 8, { shopify: 8, woocommerce: 6 }),
    ],
    relations,
    undecided: relations.filter((r) => !r.confirmed).map((r) => r.id),
    aliases: [{ names: { shopify: 'variant', woocommerce: 'variation' }, concept: 'Variant' }],
    openQuestions: [
      {
        question: 'Is a **variant** a product of its own in orders?',
        detail: 'Shopify orders point at variants.',
        options: ['variant', 'product'],
      },
    ],
    sharePath: `/model-sets/${id}`,
    shareUrl: null,
    revisePrompt: `Use the Plume connector. Call revise_model_set with id "${id}", change what you need, then submit_model_set_draft(session_id, draft, based_on="${id}").`,
    ...extra,
  };
}

export function seedSets(): StoredSet[] {
  const at = (s: ModelSet, createdAt: string, lineageId: string, ownerKey?: string): StoredSet => ({
    set: s,
    lineageId,
    ownerKey,
    createdAt,
  });
  return [
    at(
      build(SET_OFFICIAL, 'Shop', 'official', [
        orderItems(true, 'embedded'),
        productVariants(true),
      ]),
      '2026-11-16T10:00:00Z',
      'S-shop',
    ),
    // a proposal the maintainer still has to decide: release is refused until then
    at(
      build(
        SET_UNRELEASED,
        'Catalog (draft)',
        'unreleased',
        [orderItems(false, 'embedded'), productVariants(true)],
        {
          generator: 'gemini:gemini-2.5-pro',
          members: [
            { ...member('Order', 12, { shopify: 9, woocommerce: 11 }), visibility: 'unreleased' },
            {
              ...member('Product', 14, { shopify: 14, woocommerce: 13 }),
              visibility: 'unreleased',
            },
            { concept: 'Variant', modelId: 'm-variant', missing: true },
          ],
        },
      ),
      '2026-11-16T12:00:00Z',
      'S-draft',
    ),
    at(
      build(
        SET_UNLISTED,
        'Shop (my version)',
        'unlisted',
        [orderItems(true, 'embedded'), productVariants(true)],
        {
          basedOn: SET_OFFICIAL,
        },
      ),
      '2026-11-16T13:00:00Z',
      'S-mine',
      SET_OWNER_KEY,
    ),
  ];
}

export function lineageOf(all: StoredSet[], x: StoredSet): ModelLineage {
  const same = all
    .filter((y) => y.lineageId === x.lineageId && y.set.visibility !== 'discarded')
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const index = same.findIndex((y) => y.set.id === x.set.id);
  return {
    id: x.lineageId,
    version: index + 1,
    versions: same.length,
    basedOn: x.set.basedOn ?? null,
    latestId: same[same.length - 1]?.set.id ?? x.set.id,
    history: same.map((y, i) => ({
      id: y.set.id,
      version: i + 1,
      createdAt: y.createdAt,
      visibility: y.set.visibility,
    })),
  };
}

export const setJson = (all: StoredSet[], x: StoredSet): ModelSet => ({
  ...x.set,
  lineage: lineageOf(all, x),
});

export const setListItem = (all: StoredSet[], x: StoredSet): SetListItem => {
  const l = lineageOf(all, x);
  return {
    id: x.set.id,
    name: x.set.name,
    apis: x.set.inputs.map((a) => a.id),
    members: x.set.members.map((m) => m.concept),
    relations: x.set.relations.length,
    undecided: x.set.undecided.length,
    generatedAt: x.set.generatedAt,
    visibility: x.set.visibility,
    official: x.set.official,
    version: l.version,
    versions: l.versions,
    stale: x.set.stale ?? false,
  };
};

/** The result of an edit as the server would answer it: the new relations, or the refusal. */
export function applyEdits(
  base: ModelSet,
  edits: RelationEdit[],
):
  | { relations: SetRelation[] }
  | { status: 400 | 422; error: string; message: string; issues?: object[] } {
  const relations = base.relations.map((r) => ({ ...r }));
  for (const e of edits) {
    const rel = relations.find((r) => r.id === e.id);
    if (!rel) return { status: 400, error: 'bad_request', message: `No relation ${e.id}` };
    const extra = Object.keys(e).filter(
      (k) => !['id', 'kind', 'cardinality', 'embed', 'ref', 'from', 'to', 'confirmed'].includes(k),
    );
    if (extra.length)
      return {
        status: 400,
        error: 'bad_request',
        message: `Not a design field: ${extra.join(', ')}`,
      };
    const wants = { kind: e.kind ?? rel.kind, cardinality: e.cardinality ?? rel.cardinality };
    const option = (rel.editableOptions ?? []).find(
      (o) => o.kind === wants.kind && o.cardinality === wants.cardinality,
    );
    if (!option || !option.editable)
      return {
        status: 422,
        error: 'design_refused',
        message: '1 issue(s): RELATION_SHAPE_MISMATCH',
        issues: [
          {
            code: 'RELATION_SHAPE_MISMATCH',
            field: rel.id,
            api: null,
            message: option ? `That design needs: ${option.missing.join('; ')}` : 'No such design',
          },
        ],
      };
    rel.kind = option.kind;
    rel.cardinality = option.cardinality;
    rel.from = option.from;
    rel.to = option.to;
    rel.embed = option.embed;
    rel.ref = option.ref;
    rel.confirmed = e.confirmed ?? rel.confirmed;
    rel.editableOptions = (rel.editableOptions ?? []).map((o) => ({
      ...o,
      current: o.kind === option.kind && o.cardinality === option.cardinality,
    }));
  }
  return { relations };
}
