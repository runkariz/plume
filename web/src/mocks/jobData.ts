import type { DiffItem, Job, JobEvent, StepKey } from '@/api/types';

/** Sample data from the mockups pics/plume-src/04..07. */
const diffItems: DiffItem[] = [
  {
    change: 'changed',
    kind: 'endpoint',
    title: 'Create an order',
    method: 'POST',
    path: '/admin/api/latest/orders.json',
    note: '1 new parameter, description reworded',
  },
  {
    change: 'changed',
    kind: 'endpoint',
    title: 'Retrieve a list of products',
    method: 'GET',
    path: '/admin/api/latest/products.json',
    note: 'Response example changed',
  },
  {
    change: 'changed',
    kind: 'guide',
    title: 'Pagination: Link header and range searches',
    note: 'Section rewritten',
  },
  {
    change: 'new',
    kind: 'endpoint',
    title: 'Retrieve gift cards',
    method: 'GET',
    path: '/admin/api/latest/gift_cards.json',
    note: 'New endpoint',
  },
  { change: 'new', kind: 'model', title: 'Order risk assessment', note: 'New model' },
  {
    change: 'removed',
    kind: 'endpoint',
    title: 'Retrieve legacy checkouts',
    method: 'GET',
    path: '/admin/api/latest/legacy_checkouts.json',
    note: 'Removed from docs',
  },
];

export function sampleJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    apiId: 'shopify',
    displayName: 'Shopify Admin REST',
    status: 'uploaded',
    tag: 'latest',
    error: null,
    liveBuild: '2026-11-02',
    stagedBuild: '2026-11-14',
    package: {
      filename: 'shopify-package.zip',
      sizeBytes: 214 * 1024,
      files: 1118,
      contents: { endpoints: 137, models: 31, guides: 18 },
      validation: [
        {
          key: 'archive',
          title: 'Archive is safe',
          detail: 'No path traversal · only .md and .json files · within size limits',
          status: 'ok',
        },
        {
          key: 'schema',
          title: 'Known package schema',
          detail: 'manifest.json: schema 2.0',
          status: 'ok',
        },
        {
          key: 'quality',
          title: 'Quality report',
          detail: '0 blockers · 90 warnings · 24 notes',
          status: 'warn',
        },
        {
          key: 'contents',
          title: 'Contents',
          detail: '137 endpoints · 31 models · 18 guides',
          status: 'ok',
        },
      ],
      suggested: { apiId: 'shopify', displayName: 'Shopify Admin REST', tag: '2026-11-14' },
    },
    diff: null,
    plan: null,
    eval: null,
    ...overrides,
  };
}

export function withReview(job: Job): Job {
  return {
    ...job,
    status: 'reviewed',
    diff: {
      since: '2026-11-02',
      counts: { new: 12, changed: 38, removed: 3, unchanged: 359 },
      items: diffItems,
      totalItems: 53,
    },
    plan: {
      toEmbed: 50,
      total: 409,
      model: 'gemini-embedding-001',
      dimensions: 768,
      estimatedTokens: '~20k',
      estimatedCost: '< $0.01',
    },
  };
}

export function withEval(job: Job, passed = true): Job {
  return {
    ...job,
    eval: {
      gate: passed
        ? {
            passed: true,
            message: 'Staged build 2026-11-14 is at least as good as the live build 2026-11-02.',
          }
        : {
            passed: false,
            message:
              'Recall@5 dropped by more than the allowed threshold against the live build 2026-11-02. Publishing is blocked.',
          },
      metrics: [
        {
          key: 'recall',
          label: 'Recall@5',
          live: '0.93',
          staged: passed ? '0.94' : '0.81',
          delta: passed ? '+0.01' : '-0.12',
          tone: passed ? 'ok' : 'bad',
        },
        {
          key: 'mrr',
          label: 'MRR',
          live: '0.81',
          staged: passed ? '0.81' : '0.70',
          delta: passed ? 'same' : '-0.11',
          tone: passed ? 'neutral' : 'bad',
        },
        {
          key: 'invented',
          label: 'Invented endpoints',
          live: '0 / 40',
          staged: '0 / 40',
          delta: 'ok',
          tone: 'ok',
        },
        {
          key: 'chunks',
          label: 'Chunks',
          live: '400',
          staged: '409',
          delta: '+9',
          tone: 'neutral',
        },
      ],
      release: {
        version: '2026-11-14',
        knowledgeFile: 'shopify-2026-11-14.dump.gz',
        notes: '12 new · 38 changed · 3 removed',
      },
    },
  };
}

type Draft =
  | Omit<Extract<JobEvent, { type: 'log' }>, 'id'>
  | Omit<Extract<JobEvent, { type: 'step' }>, 'id'>
  | Omit<Extract<JobEvent, { type: 'progress' }>, 'id'>
  | Omit<Extract<JobEvent, { type: 'service' }>, 'id'>
  | Omit<Extract<JobEvent, { type: 'done' }>, 'id'>;

const step = (key: StepKey, status: 'running' | 'done' | 'failed', detail: string): Draft => ({
  type: 'step',
  key,
  status,
  detail,
});
const log = (t: string, source: 'plume' | 'postgres' | 'gemini', message: string): Draft => ({
  type: 'log',
  t,
  source,
  message,
});

/** The scripted build from mockup 06, ending in `staged` (or a failure at the embed step). */
export function buildScript(fail = false): Draft[] {
  const events: Draft[] = [
    step('validate', 'running', 'Checking the archive'),
    log('14:02:11', 'plume', 'Package accepted, sha256 9f2c41…'),
    step('validate', 'done', 'Package accepted · 1,118 files · 0.4 s'),
    step('chunk', 'running', 'Chunking documents'),
    log('14:02:12', 'plume', 'Chunked 409 chunks (186 documents)'),
    step('chunk', 'done', '409 chunks from 186 documents'),
    step('diff', 'running', 'Comparing with 2026-11-02'),
    log('14:02:12', 'postgres', 'Loaded build 2026-11-02, 400 chunk hashes'),
    log('14:02:13', 'plume', 'Diff: 12 new, 38 changed, 3 removed, 359 kept'),
    step('diff', 'done', '12 new · 38 changed · 3 removed · 359 kept'),
    { type: 'service', service: 'postgres', detail: 'pgvector 0.8 · 4 ms' },
    { type: 'service', service: 'gemini', detail: 'embedding-001 · 0 retries' },
    step('embed', 'running', 'Batch 1 of 4 · 0 of 50 chunks'),
    { type: 'progress', done: 0, total: 50, etaSeconds: 8 },
    log('14:02:13', 'gemini', 'Batch 1/4 · 16 chunks · 768 dims'),
    log('14:02:15', 'gemini', 'Batch 1/4 done in 1.4 s'),
    { type: 'progress', done: 16, total: 50, etaSeconds: 7 },
    step('embed', 'running', 'Batch 2 of 4 · 16 of 50 chunks'),
    log('14:02:15', 'gemini', 'Batch 2/4 · 16 chunks'),
  ];
  if (fail) {
    events.push(
      log('14:02:16', 'gemini', 'Batch 2/4 failed: 429 quota exceeded (5 retries)'),
      step('embed', 'failed', 'Batch 2 of 4 failed: quota exceeded'),
      { type: 'done', status: 'failed', message: 'Embedding failed: Gemini quota exceeded.' },
    );
    return events;
  }
  events.push(
    log('14:02:16', 'gemini', 'Batch 2/4 done in 1.3 s'),
    { type: 'progress', done: 32, total: 50, etaSeconds: 6 },
    log('14:02:17', 'postgres', 'Staged 32 chunks into chunks_next'),
    step('embed', 'running', 'Batch 3 of 4 · 32 of 50 chunks'),
    log('14:02:17', 'gemini', 'Batch 3/4 · 16 chunks'),
    { type: 'progress', done: 50, total: 50, etaSeconds: 0 },
    step('embed', 'done', '4 batches · 50 chunks embedded'),
    step('store', 'running', 'Staging in Postgres'),
    log('14:02:19', 'postgres', 'Staged 50 chunks into chunks_next'),
    step('store', 'done', 'Staged build 2026-11-14'),
    step('evaluate', 'running', '40 gold questions, answer checks'),
    log('14:02:21', 'plume', 'Eval done: recall@5 0.94, 0 invented endpoints'),
    step('evaluate', 'done', 'Recall@5 0.94 · 0 invented endpoints'),
    { type: 'done', status: 'staged' },
  );
  return events;
}

/**
 * Number of events emitted before the "mid-build" frame of mockup 06 (batch 3 of 4, 32 of 50 chunks).
 * e2e tests pause the mock stream here (localStorage key `plume-mock-pause-at` = "mid") to take a stable screenshot.
 */
export const MID_BUILD_PAUSE =
  buildScript().findIndex((e) => e.type === 'log' && e.message === 'Batch 3/4 · 16 chunks') + 1;
