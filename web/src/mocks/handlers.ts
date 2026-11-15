import { delay, http, HttpResponse } from 'msw';
import { apiBaseUrl } from '@/api/config';
import type {
  CheckCallRequest,
  GenerateRequest,
  ItemKind,
  Job,
  ModelSnapshot,
  ReviewRequest,
  SearchRequest,
} from '@/api/types';
import {
  apiRef,
  modelCandidates,
  order40Snapshot,
  productSnapshot,
  sampleSuggestions,
  snapshots,
} from './modelData';
import {
  authDetailFor,
  authFor,
  environmentsFor,
  ICON_PNG_BASE64,
  iconApis,
  mcpFor,
  triggerDetailFor,
  triggersFor,
} from './sectionData';
import { buildScript, MID_BUILD_PAUSE, sampleJob, withEval, withReview } from './jobData';
import {
  detailFor,
  sampleApis,
  sampleAsk,
  sampleCheck,
  sampleClaudePayload,
  sampleHits,
  sampleTrace,
  shopifyItems,
} from './data';

const notFound = () => HttpResponse.json({ detail: 'API not found' }, { status: 404 });

export interface MockOptions {
  /** Pause between scripted build events, in ms (0 in unit tests). */
  eventDelayMs?: number;
  /** Make the scripted build fail at the embed step. */
  failBuild?: boolean;
  /** Make the quality gate fail. */
  failGate?: boolean;
}

/** Test hook (browser only): `localStorage['plume-mock-pause-at'] = 'mid'` freezes the build stream mid-way. */
function readPauseAt(): number | null {
  try {
    return globalThis.localStorage?.getItem('plume-mock-pause-at') === 'mid'
      ? MID_BUILD_PAUSE
      : null;
  } catch {
    return null;
  }
}

interface EvidenceDoc {
  doc_id: string;
  title: string;
  endpoint: string | null;
  complete: boolean;
  fields: {
    path: string;
    type: string;
    location: string;
    required: boolean;
    description: string | null;
  }[];
}

const evidenceDocs: EvidenceDoc[] = [
  {
    doc_id: 'model:order',
    title: 'Order',
    endpoint: null,
    complete: true,
    fields: [
      {
        path: 'id',
        type: 'string',
        location: 'model',
        required: true,
        description: 'Unique identifier of the order.',
      },
      {
        path: 'number',
        type: 'string',
        location: 'model',
        required: false,
        description: 'Human-readable order reference.',
      },
      {
        path: 'total',
        type: 'string',
        location: 'model',
        required: true,
        description: 'Total amount billed…',
      },
    ],
  },
  {
    doc_id: 'endpoint:GET~/api/{version}/orders',
    title: 'List orders',
    endpoint: 'GET /api/{version}/orders',
    complete: false,
    fields: [
      { path: 'limit', type: 'integer', location: 'query', required: false, description: null },
      {
        path: 'orders[].id',
        type: 'string',
        location: 'response',
        required: false,
        description: null,
      },
    ],
  },
];

const sameSet = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

const unauthorized = () =>
  HttpResponse.json({ detail: 'Invalid or missing token' }, { status: 401 });
const isMaintainer = (req: Request) =>
  (req.headers.get('authorization') ?? '').startsWith('Bearer pl_');

export function createHandlers(base: string = apiBaseUrl(), opts: MockOptions = {}) {
  const eventDelay = opts.eventDelayMs ?? 0;
  /** In-memory job store: one sample job per upload, advanced by the endpoints below. */
  const jobs = new Map<string, Job>();
  const modelSessions = new Map<string, { apis: string[]; concept: string }>();
  const made = new Map<string, { model: ModelSnapshot; apis: string[]; concept: string }>();
  let sessionCounter = 0;
  let counter = 0;
  const guard = (req: Request, id: string) => {
    if (!isMaintainer(req)) return unauthorized();
    const job = jobs.get(id);
    return job ?? HttpResponse.json({ detail: 'Job not found' }, { status: 404 });
  };
  const encoder = new TextEncoder();
  const script = buildScript(opts.failBuild);

  return [
    http.get(`${base}/v1/models/candidates`, () => HttpResponse.json({ items: modelCandidates })),
    http.post(`${base}/v1/models/suggest`, async ({ request }) => {
      const { apis } = (await request.json()) as { apis: string[] };
      if (!Array.isArray(apis) || apis.length < 2)
        return HttpResponse.json({ detail: 'Pick at least two APIs' }, { status: 422 });
      if (apis.some((id) => !apiRef(id)))
        return HttpResponse.json({ detail: 'Unknown API in the selection' }, { status: 404 });
      return HttpResponse.json(sampleSuggestions(apis));
    }),
    // P5: the server runs no LLM. Inventory and Product already have a snapshot ("ready"); any other
    // concept opens a session that waits for a draft, which a maintainer can submit (token pl_...).
    http.post(`${base}/v1/models/generate`, async ({ request }) => {
      const body = (await request.json()) as GenerateRequest;
      const existing =
        body.concept === 'inventory'
          ? 'snap_8f3a21'
          : body.concept === 'product'
            ? 'snap_prod01'
            : [...made.values()].find(
                (m) => m.concept === body.concept && sameSet(m.apis, body.apis),
              )?.model.id;
      sessionCounter += 1;
      const sessionId = `s-mock${sessionCounter}`;
      modelSessions.set(sessionId, { apis: body.apis, concept: body.concept });
      return HttpResponse.json({
        sessionId,
        status: existing ? 'ready' : 'awaiting_draft',
        snapshotId: existing ?? null,
        inputs: body.apis.map((api) => ({ api, build: 'b-6ff6063a275d40c14e4bcdd001f1c9ae' })),
        contextUrl: `/v1/models/sessions/${sessionId}/context`,
        claudePrompt: `Use the Plume maintainer MCP: get_model_context("${sessionId}"), write the canonical ${body.concept} model for ${body.apis.join(', ')}, then submit_model_draft("${sessionId}", draft).`,
        mcpUrl: 'http://127.0.0.1:18481/mcp',
        maintainerMcpUrl: 'http://127.0.0.1:18481/maintainer/mcp',
      });
    }),
    http.get(`${base}/v1/models/sessions/:id/context`, ({ params }) => {
      const session = modelSessions.get(String(params.id));
      if (!session)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      return HttpResponse.json({
        session_id: params.id,
        concept: session.concept,
        apis: session.apis.map((api) => ({
          api,
          build: 'b-6ff6063a275d40c14e4bcdd001f1c9ae',
          documents: evidenceDocs.map((d) => ({
            doc_id: d.doc_id,
            kind: d.doc_id.split(':')[0],
            title: d.title,
            endpoint: d.endpoint,
            fields: d.fields.length,
            complete: d.complete,
          })),
        })),
        next: 'Read the fields per API with the evidence route, then write the draft.',
        instructions:
          'Write the canonical model from the documents below. Copy field names and quotes verbatim.',
        draft_format: {
          name: 'string',
          fields: [{ name: 'string', sources: '{ api: { paths, evidence } }' }],
        },
        status: 'open',
      });
    }),
    // Paged like the real route: two documents' worth of fields per page, then a cursor.
    http.get(`${base}/v1/models/sessions/:id/evidence`, ({ params, request }) => {
      const session = modelSessions.get(String(params.id));
      if (!session)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      const url = new URL(request.url);
      const api = url.searchParams.get('api') ?? '';
      if (!session.apis.includes(api))
        return HttpResponse.json(
          { error: 'bad_request', message: 'api is not in the session' },
          { status: 400 },
        );
      const cursor = Number(url.searchParams.get('cursor') ?? 0);
      const all = evidenceDocs.flatMap((d) => d.fields.map((f) => ({ doc: d, f })));
      const PAGE = 3;
      const slice = all.slice(cursor, cursor + PAGE);
      const docs = new Map<string, EvidenceDoc>();
      for (const { doc, f } of slice) {
        const hit = docs.get(doc.doc_id) ?? { ...doc, fields: [] };
        hit.fields = [...hit.fields, f];
        docs.set(doc.doc_id, hit);
      }
      const next = cursor + PAGE < all.length ? cursor + PAGE : null;
      return HttpResponse.json({
        session_id: params.id,
        api,
        build: 'b-6ff6063a275d40c14e4bcdd001f1c9ae',
        documents: [...docs.values()].map((d) => ({ ...d, source_url: null })),
        returned: slice.length,
        total_fields: all.length,
        next_cursor: next,
        missing_doc_ids: [],
      });
    }),
    http.post(`${base}/v1/models/sessions/:id/draft`, async ({ params, request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const session = modelSessions.get(String(params.id));
      if (!session)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      const draft = (await request.json()) as {
        name?: unknown;
        fields?: unknown;
        refuse?: unknown;
      };
      const issues =
        typeof draft.name !== 'string' || !Array.isArray(draft.fields) || draft.fields.length === 0
          ? [
              {
                code: 'INVALID_FORMAT',
                field: 'draft',
                api: null,
                message: 'the draft needs a name and at least one field',
              },
            ]
          : draft.refuse === 'quote'
            ? [
                {
                  code: 'QUOTE_NOT_FOUND',
                  field: 'total',
                  api: session.apis[0] ?? null,
                  message: "the quote is not in model:order: 'Total including tax.'",
                },
              ]
            : [];
      if (issues.length)
        return HttpResponse.json(
          {
            error: 'draft_refused',
            message: `${issues.length} issue(s): ${issues[0]?.code}`,
            detail: 'refused',
            accepted: false,
            issues,
          },
          { status: 422 },
        );
      const model = {
        ...productSnapshot,
        id: `m-mock${made.size + 1}`,
        name: String(draft.name),
        concept: session.concept,
        sessionId: String(params.id),
      };
      made.set(model.id, { model, apis: session.apis, concept: session.concept });
      return HttpResponse.json({ created: true, model }, { status: 201 });
    }),
    http.get(`${base}/v1/models`, ({ request }) => {
      const api = new URL(request.url).searchParams.get('api');
      const all = ['shopify', 'woocommerce', 'mirakl'];
      const seeded: { m: ModelSnapshot; concept: string; apis: string[] }[] = [
        { m: order40Snapshot, concept: 'Order', apis: all },
      ];
      const inventory = snapshots['snap_8f3a21'];
      if (inventory) seeded.unshift({ m: inventory, concept: 'inventory', apis: all });
      const items = [
        ...[...made.values()].map((m) => ({
          id: m.model.id,
          name: m.model.name,
          concept: m.concept,
          apis: m.apis,
          generatedAt: '2026-11-15T01:00:00Z',
          stale: false,
        })),
        ...seeded.map((x) => ({
          id: x.m.id,
          name: x.m.name,
          concept: x.concept,
          apis: x.apis,
          generatedAt: x.m.generatedAt,
          stale: x.m.stale ?? false,
          staleInputs: x.m.staleInputs ?? [],
        })),
      ].filter((m) => !api || m.apis.includes(api));
      return HttpResponse.json({ items });
    }),
    http.get(`${base}/v1/models/:id`, ({ params }) => {
      const id = String(params.id);
      const snap = snapshots[id] ?? made.get(id)?.model;
      return snap
        ? HttpResponse.json(snap)
        : HttpResponse.json({ error: 'not_found', message: 'Snapshot not found' }, { status: 404 });
    }),
    http.get(`${base}/v1/maintainer/me`, ({ request }) =>
      isMaintainer(request) ? HttpResponse.json({ name: 'maintainer' }) : unauthorized(),
    ),
    http.post(`${base}/v1/packages`, async ({ request }) => {
      if (!isMaintainer(request)) return unauthorized();
      // The mock only needs the file name: read it from the raw multipart body (no multipart parser needed).
      const filename = /filename="([^"]*)"/.exec(await request.text())?.[1];
      if (!filename) return HttpResponse.json({ detail: 'file is required' }, { status: 400 });
      if (!filename.endsWith('.zip'))
        return HttpResponse.json({ detail: 'Only .zip packages are accepted' }, { status: 415 });
      counter += 1;
      const job = sampleJob({ id: `job-${counter}` });
      job.package.filename = filename;
      jobs.set(job.id, job);
      return HttpResponse.json(job, { status: 201 });
    }),
    http.get(`${base}/v1/jobs/:id`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      return job instanceof Response ? job : HttpResponse.json(job);
    }),
    http.post(`${base}/v1/jobs/:id/review`, async ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      const body = (await request.json()) as ReviewRequest;
      const next = withReview({
        ...job,
        apiId: body.apiId,
        displayName: body.displayName,
        stagedBuild: body.tag,
      });
      jobs.set(next.id, next);
      return HttpResponse.json(next);
    }),
    http.post(`${base}/v1/jobs/:id/build`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      const next: Job = { ...job, status: 'building' };
      jobs.set(next.id, next);
      return HttpResponse.json(next, { status: 202 });
    }),
    http.get(`${base}/v1/jobs/:id/events`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      const from = Number(request.headers.get('last-event-id') ?? 0);
      const replay = job.status !== 'building';
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          const pauseAt = readPauseAt();
          for (let i = from; i < script.length; i += 1) {
            if (pauseAt !== null && i === pauseAt) {
              // hold the stream open (never finishes) until the client leaves
              await new Promise<void>((resolve) =>
                request.signal.addEventListener('abort', () => resolve()),
              );
              break;
            }
            if (!replay && eventDelay > 0) await delay(eventDelay);
            const draft = script[i];
            if (!draft) break;
            const e = { ...draft, id: String(i + 1) };
            controller.enqueue(
              encoder.encode(`id: ${i + 1}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`),
            );
          }
          const last = script[script.length - 1];
          const ok = last?.type === 'done' && last.status === 'staged';
          const current = jobs.get(job.id) ?? job;
          if (current.status === 'building')
            jobs.set(
              job.id,
              ok
                ? withEval({ ...current, status: 'staged' }, !opts.failGate)
                : { ...current, status: 'failed' },
            );
          controller.close();
        },
      });
      return new HttpResponse(stream, {
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      });
    }),
    http.post(`${base}/v1/jobs/:id/publish`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      if (job.status !== 'staged' || !job.eval?.gate.passed)
        return HttpResponse.json({ detail: 'The quality gate has not passed' }, { status: 409 });
      const next: Job = { ...job, status: 'published' };
      jobs.set(next.id, next);
      return HttpResponse.json(next);
    }),
    http.post(`${base}/v1/jobs/:id/discard`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      const next: Job = { ...job, status: 'discarded' };
      jobs.set(next.id, next);
      return HttpResponse.json(next);
    }),
    http.get(`${base}/v1/jobs/:id/dump`, ({ params, request }) => {
      const job = guard(request, String(params.id));
      if (job instanceof Response) return job;
      return new HttpResponse(new Blob(['mock dump']), {
        headers: {
          'Content-Type': 'application/gzip',
          'Content-Disposition': 'attachment; filename="shopify-2026-11-14.dump.gz"',
        },
      });
    }),
    http.get(`${base}/v1/apis`, () => HttpResponse.json({ items: sampleApis })),
    http.get(`${base}/v1/apis/:id`, ({ params }) => {
      const found = detailFor(String(params.id));
      return found ? HttpResponse.json(found) : notFound();
    }),
    // A stored document (what a citation points at). The mock builds one from the id.
    http.get(`${base}/v1/apis/:id/documents/*`, ({ params, request }) => {
      const api = String(params.id);
      if (!detailFor(api)) return notFound();
      const prefix = `/v1/apis/${api}/documents/`;
      const docId = decodeURIComponent(new URL(request.url).pathname.split(prefix)[1] ?? '');
      const item = shopifyItems.find((i) => i.id === docId); // the Browse sample items resolve to their own detail
      const kind = item?.kind ?? docId.split(':')[0] ?? 'document';
      const path = item?.path ?? (docId.includes('~') ? docId.split('~')[1] : null);
      const method =
        item?.method ?? (docId.includes('~') ? (docId.split(':')[1]?.split('~')[0] ?? null) : null);
      return HttpResponse.json({
        api,
        build: 'b-6ff6063a275d40c14e4bcdd001f1c9ae',
        docsAsOf: '2026-11-14',
        id: docId,
        kind,
        title: item?.title ?? docId.split(/[:~]/).pop() ?? docId,
        resource: item?.resource ?? 'orders',
        method,
        path: path ?? null,
        deprecated: false,
        complete: docId.includes('partial') ? false : true,
        sourceUrl: `https://docs.example.com/${api}/${kind}`,
        anchor: '#section',
        text: `# ${docId}\n\nSample text for this document in the mock backend.\nTotal amount billed for the order.`,
        fields: [
          ...(path?.includes('{') || kind === 'model'
            ? [
                {
                  name: 'order_id',
                  location: kind === 'model' ? 'model' : 'path',
                  type: 'string',
                  required: true,
                  description: 'Unique identifier of the order.',
                },
              ]
            : []),
          ...(kind === 'endpoint'
            ? [
                {
                  name: 'limit',
                  location: 'query',
                  type: 'integer',
                  required: false,
                  description: null,
                },
                {
                  name: 'X-Access-Token',
                  location: 'header',
                  type: 'string',
                  required: true,
                  description: 'Authentication token',
                },
              ]
            : []),
          ...(kind === 'endpoint' && method && method !== 'GET'
            ? [
                {
                  name: 'order',
                  location: 'body',
                  type: 'object',
                  required: true,
                  description: null,
                },
                {
                  name: 'order.total',
                  location: 'body',
                  type: 'string',
                  required: false,
                  description: 'Total amount billed.',
                },
              ]
            : []),
          ...(kind === 'endpoint'
            ? [
                {
                  name: 'orders[].id',
                  location: 'response',
                  type: 'string',
                  required: false,
                  description: null,
                },
              ]
            : []),
        ],
        tags: kind === 'endpoint' ? ['v3', 'orders'] : [],
        raw:
          kind === 'guide'
            ? null
            : { operationId: docId, summary: 'Sample source JSON from the package' },
        rawTruncated: false,
        responses:
          kind === 'endpoint'
            ? [
                { status: 200, description: 'The order.' },
                { status: 404, description: 'No such order.' },
              ]
            : [],
        scopes: [],
      });
    }),
    // package sections (shaped like the real API)
    http.get(`${base}/v1/apis/:id/auth`, ({ params }) =>
      detailFor(String(params.id)) ? HttpResponse.json(authFor(String(params.id))) : notFound(),
    ),
    http.get(`${base}/v1/apis/:id/auth/:scheme`, ({ params }) => {
      const d =
        detailFor(String(params.id)) && authDetailFor(String(params.id), String(params.scheme));
      return d
        ? HttpResponse.json(d)
        : HttpResponse.json(
            { error: 'not_found', message: 'No such auth scheme' },
            { status: 404 },
          );
    }),
    http.get(`${base}/v1/apis/:id/triggers`, ({ params, request }) => {
      if (!detailFor(String(params.id))) return notFound();
      const u = new URL(request.url);
      return HttpResponse.json(
        triggersFor(
          String(params.id),
          Number(u.searchParams.get('limit') ?? 50),
          Number(u.searchParams.get('offset') ?? 0),
        ),
      );
    }),
    http.get(`${base}/v1/apis/:id/triggers/*`, ({ params, request }) => {
      const prefix = `/v1/apis/${String(params.id)}/triggers/`;
      const key = decodeURIComponent(new URL(request.url).pathname.split(prefix)[1] ?? '');
      const d = triggerDetailFor(String(params.id), key);
      return d
        ? HttpResponse.json(d)
        : HttpResponse.json({ error: 'not_found', message: 'No such event' }, { status: 404 });
    }),
    http.get(`${base}/v1/apis/:id/mcp`, ({ params }) =>
      detailFor(String(params.id)) ? HttpResponse.json(mcpFor(String(params.id))) : notFound(),
    ),
    http.get(`${base}/v1/apis/:id/environments`, ({ params }) =>
      detailFor(String(params.id))
        ? HttpResponse.json(environmentsFor(String(params.id)))
        : notFound(),
    ),
    http.get(`${base}/v1/apis/:id/icon`, ({ params }) => {
      if (!iconApis.has(String(params.id)))
        return HttpResponse.json(
          { error: 'not_found', message: 'This package has no icon' },
          { status: 404 },
        );
      const bytes = Uint8Array.from(atob(ICON_PNG_BASE64), (c) => c.charCodeAt(0));
      return new HttpResponse(bytes, {
        headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' },
      });
    }),
    http.get(`${base}/v1/apis/:id/items`, ({ params, request }) => {
      if (!detailFor(String(params.id))) return notFound();
      const url = new URL(request.url);
      const kind = url.searchParams.get('kind') as ItemKind | null;
      const q = (url.searchParams.get('q') ?? '').toLowerCase();
      const limit = Number(url.searchParams.get('limit') ?? 50);
      const matching = shopifyItems.filter(
        (i) =>
          (!kind || i.kind === kind) &&
          (!q ||
            `${i.method ?? ''} ${i.path ?? ''} ${i.title} ${i.resource}`.toLowerCase().includes(q)),
      );
      return HttpResponse.json({ items: matching.slice(0, limit), total: matching.length });
    }),
    http.post(`${base}/v1/apis/:id/search`, async ({ params, request }) => {
      if (!detailFor(String(params.id))) return notFound();
      const body = (await request.json()) as SearchRequest;
      const hits = sampleHits.filter((h) => body.kind === 'all' || h.kind === body.kind);
      return HttpResponse.json({
        api: String(params.id),
        docsAsOf: '2026-11-14',
        results: hits.slice(0, body.topK),
        trace: sampleTrace,
        totalMs: 47,
        claudePayload: sampleClaudePayload,
      });
    }),
    http.post(`${base}/v1/apis/:id/ask`, async ({ params, request }) => {
      if (!detailFor(String(params.id))) return notFound();
      const body = (await request.json()) as { question: string };
      return HttpResponse.json(sampleAsk(body.question));
    }),
    http.post(`${base}/v1/apis/:id/check-call`, async ({ params, request }) => {
      if (!detailFor(String(params.id))) return notFound();
      const body = (await request.json()) as CheckCallRequest;
      return HttpResponse.json(sampleCheck(body.method, body.path, body.params));
    }),
  ];
}
