import type {
  DraftIssue,
  ModelJob,
  ModelJobEvent,
  ModelLineage,
  ModelListItem,
  ModelSnapshot,
  ModelVisibility,
} from '@/api/types';
import { inventorySnapshot, order40Snapshot, productSnapshot } from './modelData';
import { iconApis } from './sectionData';

/** What the mock server keeps for a model: the snapshot plus the access fields plume-6f's API adds. */
export interface StoredModel {
  model: ModelSnapshot;
  apis: string[];
  concept: string;
  visibility: ModelVisibility;
  lineageId: string;
  origin: 'user' | 'maintainer';
  generator: string;
  basedOn: string | null;
  ownerKey?: string;
  createdAt: string;
}

export interface MockSession {
  apis: string[];
  concept: string;
  basedOn: string | null;
  snapshotId: string | null;
}

export interface MockJob {
  job: ModelJob;
  events: ModelJobEvent[];
}

const ALL = ['shopify', 'woocommerce', 'mirakl'];

/** A fixed unlisted model (its link is its id) with a 3-version lineage, for the share and lineage pages. */
export const UNLISTED_V3 = 'u-3f9a0c71d2e84b5f9a6c1d7e8b2a4c60';
const UNLISTED_V1 = 'u-1a7e5d93c04b48d2b8f6e0a39c1d7f52';
const UNLISTED_V2 = 'u-2b8c6e04d15c59e3c9a7f1b40d2e8a63';
/** A fixed unreleased model, the maintainer's review page. */
export const UNRELEASED = 'm-unrel0a1b2c3d4e5f60718293a4b5c6d7e8f';
/** The owner key of the unlisted lineage above (tests put it in localStorage to see "Your models"). */
export const DEMO_OWNER_KEY = 'ok-demo-3f9a0c71d2e84b5f';

const seed = (
  model: ModelSnapshot,
  concept: string,
  extra: Partial<StoredModel> & Pick<StoredModel, 'visibility' | 'lineageId'>,
): StoredModel => ({
  model,
  apis: ALL,
  concept,
  origin: 'maintainer',
  generator: 'claude',
  basedOn: null,
  createdAt: model.generatedAt,
  ...extra,
});

function unlisted(id: string, name: string, at: string, basedOn: string | null): StoredModel {
  return seed({ ...inventorySnapshot, id, name, generatedAt: at }, 'inventory', {
    visibility: 'unlisted',
    lineageId: 'L-demo',
    origin: 'user',
    basedOn,
    ownerKey: DEMO_OWNER_KEY,
  });
}

export function seedModels(): StoredModel[] {
  return [
    seed(inventorySnapshot, 'inventory', { visibility: 'official', lineageId: 'L-inventory' }),
    seed(productSnapshot, 'product', { visibility: 'official', lineageId: 'L-product' }),
    seed(order40Snapshot, 'Order', { visibility: 'official', lineageId: 'L-order' }),
    unlisted(UNLISTED_V1, 'Inventory, with a returns count', '2026-11-14T15:00:00Z', 'snap_8f3a21'),
    unlisted(UNLISTED_V2, 'Inventory, with a returns count', '2026-11-14T16:00:00Z', UNLISTED_V1),
    unlisted(UNLISTED_V3, 'Inventory, with a returns count', '2026-11-14T17:00:00Z', UNLISTED_V2),
    seed({ ...productSnapshot, id: UNRELEASED, name: 'Return' }, 'return', {
      visibility: 'unreleased',
      lineageId: 'L-return',
      generator: 'gemini:gemini-2.5-pro',
      createdAt: '2026-11-15T07:00:00Z',
    }),
  ];
}

export function lineageOf(all: StoredModel[], m: StoredModel): ModelLineage {
  const same = all
    .filter((x) => x.lineageId === m.lineageId && x.visibility !== 'discarded')
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const index = same.findIndex((x) => x.model.id === m.model.id);
  return {
    id: m.lineageId,
    version: index === -1 ? same.length + 1 : index + 1,
    versions: Math.max(same.length, index + 1),
    basedOn: m.basedOn,
    latestId: same[same.length - 1]?.model.id ?? m.model.id,
    history: same.map((x, i) => ({
      id: x.model.id,
      version: i + 1,
      createdAt: x.createdAt,
      visibility: x.visibility,
    })),
  };
}

const REVISE = (m: StoredModel) =>
  `Use the Plume connector. Call revise_model with id "${m.model.id}" to start from the ${m.model.name} model, ` +
  `change what you need, then submit the result with submit_model_draft(session_id, draft, based_on="${m.model.id}"). ` +
  `Plume checks every citation before it stores the new version.`;

/** The model JSON the API sends: the snapshot plus visibility, lineage, share path and the revise prompt. */
export function decorate(all: StoredModel[], m: StoredModel): ModelSnapshot {
  return {
    ...m.model,
    // an API whose package has an icon gets its route (the others send null)
    inputs: m.model.inputs.map((i) => ({
      ...i,
      logo: { ...i.logo, url: iconApis.has(i.id) ? `/v1/apis/${i.id}/icon` : null },
    })),
    visibility: m.visibility,
    official: m.visibility === 'official',
    origin: m.origin,
    generator: m.generator,
    lineage: lineageOf(all, m),
    sharePath: `/models/${m.model.id}`,
    shareUrl: null,
    revisePrompt: REVISE(m),
  };
}

export function listItem(all: StoredModel[], m: StoredModel): ModelListItem {
  const l = lineageOf(all, m);
  return {
    id: m.model.id,
    name: m.model.name,
    concept: m.concept,
    apis: m.apis,
    generatedAt: m.model.generatedAt,
    official: m.visibility === 'official',
    visibility: m.visibility,
    version: l.version,
    versions: l.versions,
    stale: m.model.stale ?? false,
    staleInputs: m.model.staleInputs ?? [],
  };
}

/** The scripted server-side generation. `shipment` is refused once first; `customer` ends in a failure. */
export function jobScript(
  jobId: string,
  apis: string[],
  concept: string,
  snapshotId: string,
): { events: ModelJobEvent[]; status: ModelJob['status'] } {
  const issues: DraftIssue[] = [
    {
      code: 'QUOTE_NOT_FOUND',
      field: 'carrier',
      api: apis[0] ?? null,
      message: "the quote is not in model:shipment: 'Carrier used for delivery.'",
    },
  ];
  if (concept === 'customer')
    return {
      status: 'failed',
      events: [
        { type: 'queued', jobId },
        { type: 'started', apis, concept },
        { type: 'context', documents: 12, fields: 214 },
        { type: 'round', n: 1, of: 3 },
        { type: 'refused', round: 1, issues },
        { type: 'round', n: 2, of: 3 },
        { type: 'refused', round: 2, issues },
        { type: 'round', n: 3, of: 3 },
        { type: 'refused', round: 3, issues },
        {
          type: 'failed',
          code: 'draft_refused',
          message: 'No accepted draft after 3 rounds.',
        },
        { type: 'done', status: 'failed', snapshotId: null },
      ],
    };
  return {
    status: 'succeeded',
    events: [
      { type: 'queued', jobId },
      { type: 'started', apis, concept },
      { type: 'context', documents: 12, fields: 214 },
      { type: 'round', n: 1, of: 3 },
      ...(concept === 'shipment'
        ? ([
            { type: 'refused', round: 1, issues },
            { type: 'round', n: 2, of: 3 },
          ] as ModelJobEvent[])
        : []),
      { type: 'accepted', snapshotId },
      { type: 'done', status: 'succeeded', snapshotId },
    ],
  };
}
