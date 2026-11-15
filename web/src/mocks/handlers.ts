import { delay, http, HttpResponse } from 'msw';
import { apiBaseUrl } from '@/api/config';
import type {
  CheckCallRequest,
  GenerateRequest,
  ItemKind,
  Job,
  RelationEdit,
  ReviewRequest,
  SearchRequest,
  SetAlias,
  SetSessionRequest,
  SuggestQuery,
} from '@/api/types';
import { apiRef, modelCandidates, productSnapshot, sampleSuggestions } from './modelData';
import { relatedFor } from './relatedData';
import {
  applyEdits,
  newSet,
  seedSets,
  lineageOf as lineageOfSet,
  setJson,
  setListItem,
  type StoredSet,
} from './setStore';
import {
  decorate,
  jobScript,
  listItem,
  seedModels,
  setJobScript,
  supersedable,
  type MockJob,
  type MockSession,
  type StoredModel,
} from './modelStore';
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

/** The package icon route of an API that has one (`logo.url` is null for the others, as the real API sends). */
function withIcon<
  T extends { id: string; logo: { text: string; color: string; url?: string | null } },
>(a: T): T {
  return { ...a, logo: { ...a.logo, url: iconApis.has(a.id) ? `/v1/apis/${a.id}/icon` : null } };
}

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
/** localStorage `plume-mock-hold-job` = "1": a model job stops at its first heartbeat and stays running (screenshots). */
function holdJobAtHeartbeat(): boolean {
  try {
    return globalThis.localStorage?.getItem('plume-mock-hold-job') === '1';
  } catch {
    return false;
  }
}

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
  const modelSessions = new Map<string, MockSession>();
  /** Every model of the mock server, seeded ones included, with who may see it. */
  const models = new Map<string, StoredModel>(seedModels().map((m) => [m.model.id, m]));
  const allModels = () => [...models.values()];
  const modelJobs = new Map<string, MockJob>();
  /** The model sets of the mock server, seeded ones included. */
  const sets = new Map<string, StoredSet>(seedSets().map((x) => [x.set.id, x]));
  const allSets = () => [...sets.values()];
  /** Set sessions: what Claude is filling (a set is stored when a draft is submitted for one). */
  const setSessions = new Map<
    string,
    { apis: string[]; concepts: string[]; aliases: SetAlias[]; setId: string | null }
  >();
  let jobCounter = 0;
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
    http.get(`${base}/v1/models/candidates`, () =>
      HttpResponse.json({ items: modelCandidates.map(withIcon) }),
    ),
    http.post(`${base}/v1/models/suggest`, async ({ request }) => {
      const body = (await request.json()) as { apis: string[] } & SuggestQuery;
      const { apis } = body;
      if (!Array.isArray(apis) || apis.length < 2)
        return HttpResponse.json({ detail: 'Pick at least two APIs' }, { status: 422 });
      if (apis.some((id) => !apiRef(id)))
        return HttpResponse.json({ detail: 'Unknown API in the selection' }, { status: 404 });
      if ((body.require ?? []).some((id) => !apis.includes(id)))
        return HttpResponse.json(
          { error: 'bad_request', message: 'require must be a subset of apis' },
          { status: 400 },
        );
      const r = sampleSuggestions(apis, body);
      return HttpResponse.json({ ...r, apis: r.apis.map(withIcon) });
    }),
    // W12: signed in, "Generate" runs on the server (a job, 202); without the token it is the Claude session and the
    // model is stored unlisted. `ready` only names a model the caller may see (official, or unreleased with the token).
    // Mock behaviour by concept: `refund` = no server model key (503), `customer` = the job fails, `shipment` = refused once.
    http.post(`${base}/v1/models/generate`, async ({ request }) => {
      const body = (await request.json()) as GenerateRequest;
      const maintainer = isMaintainer(request);
      const engine = body.engine ?? (maintainer ? 'server' : 'claude');
      if (engine === 'server' && !maintainer)
        return HttpResponse.json(
          { error: 'unauthorized', message: 'Sign in as a maintainer to generate on the server.' },
          { status: 401 },
        );
      const existing = allModels().find(
        (m) =>
          m.concept.toLowerCase() === body.concept.toLowerCase() &&
          sameSet(m.apis, body.apis) &&
          !m.model.stale &&
          (m.visibility === 'official' || (maintainer && m.visibility === 'unreleased')),
      )?.model.id;
      if (engine === 'server' && !existing) {
        if (body.concept === 'refund')
          return HttpResponse.json(
            {
              error: 'llm_unavailable',
              message: 'Server-side generation is not configured on this Plume.',
            },
            { status: 503 },
          );
        jobCounter += 1;
        const jobId = `mj-mock${jobCounter}`;
        const snapshotId = `m-job${jobCounter}`;
        const { events, status } = jobScript(jobId, body.apis, body.concept, snapshotId);
        modelJobs.set(jobId, {
          events,
          job: {
            jobId,
            status: 'queued',
            apis: body.apis,
            concept: body.concept,
            round: 0,
            maxRounds: 3,
            snapshotId: null,
            error: null,
            createdAt: '2026-11-15T08:00:00Z',
            updatedAt: '2026-11-15T08:00:00Z',
          },
        });
        void status;
        return HttpResponse.json(
          { jobId, status: 'queued', eventsUrl: `/v1/models/jobs/${jobId}/events` },
          { status: 202 },
        );
      }
      sessionCounter += 1;
      const sessionId = `s-mock${sessionCounter}`;
      modelSessions.set(sessionId, {
        apis: body.apis,
        concept: body.concept,
        basedOn: null,
        snapshotId: null,
      });
      return HttpResponse.json({
        sessionId,
        status: existing ? 'ready' : 'awaiting_draft',
        snapshotId: existing ?? null,
        inputs: body.apis.map((api) => ({ api, build: 'b-6ff6063a275d40c14e4bcdd001f1c9ae' })),
        contextUrl: `/v1/models/sessions/${sessionId}/context`,
        claudePrompt: `Use the Plume connector: get_model_context("${sessionId}"), write the canonical ${body.concept} model for ${body.apis.join(', ')}, then submit_model_draft("${sessionId}", draft).`,
        mcpUrl: 'http://127.0.0.1:18481/mcp',
        maintainerMcpUrl: maintainer ? 'http://127.0.0.1:18481/maintainer/mcp' : undefined,
      });
    }),
    http.get(`${base}/v1/models/sessions/:id`, ({ params }) => {
      const session = modelSessions.get(String(params.id));
      if (!session)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      return HttpResponse.json({
        sessionId: params.id,
        status: session.snapshotId ? 'submitted' : 'open',
        snapshotId: session.snapshotId,
        visibility: session.snapshotId
          ? (models.get(session.snapshotId)?.visibility ?? null)
          : null,
        apis: session.apis,
        concept: session.concept,
        basedOn: session.basedOn,
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
      // open to everyone, but a token that is sent and is not valid is refused
      if (request.headers.get('authorization') && !isMaintainer(request))
        return HttpResponse.json(
          { error: 'unauthorized', message: 'The token is not valid.' },
          { status: 401 },
        );
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
      // Open to everyone: with the token the model is stored unreleased, without it unlisted (its link is its id).
      // A new lineage returns an ownerKey once; a revision of a model that is not official stays in its lineage.
      const maintainer = isMaintainer(request);
      const basedOn = new URL(request.url).searchParams.get('basedOn') ?? session.basedOn;
      const base = basedOn ? models.get(basedOn) : undefined;
      const sameLineage = base && base.visibility !== 'official' ? base : undefined;
      const n = models.size + 1;
      const id = maintainer ? `m-mock${n}` : `u-mock${String(n).padStart(28, '0')}`;
      const ownerKey = maintainer || sameLineage ? undefined : `ok-mock${n}`;
      const stored: StoredModel = {
        model: {
          ...productSnapshot,
          id,
          name: String(draft.name),
          concept: session.concept,
          sessionId: String(params.id),
          generatedAt: '2026-11-15T09:00:00Z',
        },
        apis: session.apis,
        concept: session.concept,
        visibility: maintainer ? 'unreleased' : 'unlisted',
        lineageId: sameLineage?.lineageId ?? `L-${id}`,
        origin: maintainer ? 'maintainer' : 'user',
        generator: 'claude',
        basedOn: base?.model.id ?? null,
        ownerKey: ownerKey ?? sameLineage?.ownerKey,
        createdAt: new Date(Date.UTC(2026, 10, 15, 9, 0, models.size)).toISOString(),
      };
      models.set(id, stored);
      session.snapshotId = id;
      return HttpResponse.json(
        {
          created: true,
          model: decorate(allModels(), stored),
          visibility: stored.visibility,
          ...(ownerKey ? { ownerKey } : {}),
        },
        { status: 201 },
      );
    }),
    http.get(`${base}/v1/models`, ({ request }) => {
      const url = new URL(request.url);
      const api = url.searchParams.get('api');
      const want = url.searchParams.get('visibility');
      const maintainer = isMaintainer(request);
      const all = allModels();
      // the public list is the latest official version of each lineage; the token can ask for the others
      const vis = maintainer && want ? want : 'official';
      let rows = all.filter((m) => vis === 'all' || m.visibility === vis);
      // one official model per concept and API set: the newest (the server's rule; a lineage shares both)
      if (vis === 'official')
        rows = rows.filter(
          (m) =>
            !rows.some(
              (o) =>
                o !== m &&
                o.createdAt > m.createdAt &&
                o.concept.toLowerCase() === m.concept.toLowerCase() &&
                sameSet(o.apis, m.apis),
            ),
        );
      rows = rows
        .filter((m) => !api || m.apis.includes(api))
        .sort((x, y) => y.createdAt.localeCompare(x.createdAt));
      return HttpResponse.json({ items: rows.map((m) => listItem(all, m)) });
    }),
    http.post(`${base}/v1/models/mine`, async ({ request }) => {
      const { ownerKeys } = (await request.json()) as { ownerKeys?: string[] };
      const keys = Array.isArray(ownerKeys) ? ownerKeys : [];
      const all = allModels();
      const mine = all
        .filter((m) => m.ownerKey && keys.includes(m.ownerKey) && m.visibility !== 'discarded')
        .filter(
          (m, _i, rows) =>
            !rows.some((o) => o.lineageId === m.lineageId && o.createdAt > m.createdAt),
        )
        .sort((x, y) => y.createdAt.localeCompare(x.createdAt));
      return HttpResponse.json({ items: mine.map((m) => listItem(all, m)) });
    }),
    http.get(`${base}/v1/models/jobs/:id`, ({ params, request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const j = modelJobs.get(String(params.id));
      return j
        ? HttpResponse.json(j.job)
        : HttpResponse.json({ error: 'not_found', message: 'No such job' }, { status: 404 });
    }),
    http.get(`${base}/v1/models/jobs/:id/events`, ({ params, request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const j = modelJobs.get(String(params.id));
      if (!j)
        return HttpResponse.json({ error: 'not_found', message: 'No such job' }, { status: 404 });
      const from = Number(request.headers.get('last-event-id') ?? 0);
      const replay = j.job.status === 'succeeded' || j.job.status === 'failed';
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (let i = from; i < j.events.length; i += 1) {
            if (!replay && eventDelay > 0) await delay(eventDelay);
            const e = j.events[i];
            if (!e) break;
            const { type, ...data } = e;
            if (e.type === 'round') j.job = { ...j.job, status: 'running', round: e.n };
            if (e.type === 'accepted' && e.setId && !sets.has(e.setId)) {
              const s = newSet(e.setId, j.job.concept.split('+'), j.job.apis, 'unreleased', {
                generator: 'gemini:gemini-2.5-pro',
              });
              sets.set(e.setId, s);
            }
            if (e.type === 'accepted' && e.snapshotId && !models.has(e.snapshotId))
              models.set(e.snapshotId, {
                model: {
                  ...productSnapshot,
                  id: e.snapshotId,
                  name: j.job.concept.charAt(0).toUpperCase() + j.job.concept.slice(1),
                  concept: j.job.concept,
                  generatedAt: '2026-11-15T08:05:00Z',
                },
                apis: j.job.apis,
                concept: j.job.concept,
                visibility: 'unreleased',
                lineageId: `L-${e.snapshotId}`,
                origin: 'maintainer',
                generator: 'gemini:gemini-2.5-pro',
                basedOn: null,
                createdAt: '2026-11-15T08:05:00Z',
              });
            if (e.type === 'failed') j.job = { ...j.job, status: 'failed', error: e.message };
            if (e.type === 'done')
              j.job = {
                ...j.job,
                status: e.status,
                snapshotId: e.snapshotId,
                setId: e.setId ?? null,
              };
            controller.enqueue(
              encoder.encode(`id: ${i + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`),
            );
            if (e.type === 'heartbeat' && holdJobAtHeartbeat()) {
              // the model call is still in flight: hold the stream open until the client leaves
              await new Promise<void>((resolve) =>
                request.signal.addEventListener('abort', () => resolve()),
              );
              return;
            }
          }
          controller.close();
        },
      });
      return new HttpResponse(stream, {
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      });
    }),
    http.get(`${base}/v1/models/:id`, ({ params, request }) => {
      const stored = models.get(String(params.id));
      // unreleased and discarded models are not leaked: 404 without the token
      if (
        !stored ||
        ((stored.visibility === 'unreleased' || stored.visibility === 'discarded') &&
          !isMaintainer(request))
      )
        return HttpResponse.json(
          { error: 'not_found', message: 'Snapshot not found' },
          { status: 404 },
        );
      return HttpResponse.json(decorate(allModels(), stored));
    }),
    http.get(`${base}/v1/models/:id/supersedable`, ({ params, request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const stored = models.get(String(params.id));
      if (!stored)
        return HttpResponse.json(
          { error: 'not_found', message: 'Snapshot not found' },
          { status: 404 },
        );
      return HttpResponse.json({ items: supersedable(allModels(), stored) });
    }),
    http.post(`${base}/v1/models/:id/supersede`, async ({ params, request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const stored = models.get(String(params.id));
      if (!stored)
        return HttpResponse.json(
          { error: 'not_found', message: 'Snapshot not found' },
          { status: 404 },
        );
      const body = (await request.json().catch(() => ({}))) as { supersedes?: unknown };
      const ids = Array.isArray(body.supersedes) ? body.supersedes : [];
      if (ids.length === 0)
        return HttpResponse.json(
          { error: 'invalid_request', message: 'Name at least one model to supersede.' },
          { status: 400 },
        );
      const valid = new Set(supersedable(allModels(), stored).map((c) => c.id));
      const bad = ids.filter((x) => typeof x !== 'string' || !valid.has(x));
      if (stored.visibility !== 'official' || bad.length)
        return HttpResponse.json(
          {
            error: 'invalid_state',
            message:
              stored.visibility !== 'official'
                ? 'Only an official model can supersede others.'
                : `Not official models of this concept: ${bad.join(', ')}`,
          },
          { status: 409 },
        );
      for (const id of ids as string[]) {
        const old = models.get(id);
        if (old) {
          old.visibility = 'superseded';
          old.supersededBy = stored.model.id;
          old.supersededAt = '2026-11-16T12:30:00Z';
        }
      }
      return HttpResponse.json(decorate(allModels(), stored));
    }),
    ...(['release', 'discard'] as const).map((action) =>
      http.post(`${base}/v1/models/:id/${action}`, async ({ params, request }) => {
        if (!isMaintainer(request))
          return HttpResponse.json(
            { error: 'unauthorized', message: 'Missing or invalid token' },
            { status: 401 },
          );
        const stored = models.get(String(params.id));
        if (!stored)
          return HttpResponse.json(
            { error: 'not_found', message: 'Snapshot not found' },
            { status: 404 },
          );
        if (stored.visibility !== 'unreleased')
          return HttpResponse.json(
            { error: 'invalid_state', message: `Only an unreleased model can be ${action}d.` },
            { status: 409 },
          );
        // release may name the official models of the same concept it replaces: every one must be such a model
        const body = (await request.json().catch(() => ({}))) as { supersedes?: unknown };
        const replaced =
          action === 'release' && Array.isArray(body.supersedes) ? body.supersedes : [];
        const valid = new Set(supersedable(allModels(), stored).map((c) => c.id));
        const bad = replaced.filter((x) => typeof x !== 'string' || !valid.has(x));
        if (bad.length)
          return HttpResponse.json(
            {
              error: 'invalid_state',
              message: `Not official models of this concept: ${bad.join(', ')}`,
            },
            { status: 409 },
          );
        stored.visibility = action === 'release' ? 'official' : 'discarded';
        if (replaced.length) {
          for (const id of replaced as string[]) {
            const old = models.get(id);
            if (old) {
              old.visibility = 'superseded'; // readable by id, out of the lists
              old.supersededBy = stored.model.id;
              old.supersededAt = '2026-11-16T12:00:00Z';
            }
          }
        }
        return HttpResponse.json(decorate(allModels(), stored));
      }),
    ),
    // ---- related concepts, and creating a set: for Claude (a session) or on the server (a job, maintainer) ----
    http.post(`${base}/v1/models/suggest-related`, async ({ request }) => {
      const body = (await request.json()) as {
        apis: string[];
        concept: string;
        limit?: number;
        offset?: number;
      };
      if (!Array.isArray(body.apis) || body.apis.length < 2 || !body.concept)
        return HttpResponse.json(
          { error: 'invalid_request', message: 'Give two or more APIs and a concept.' },
          { status: 422 },
        );
      return HttpResponse.json(relatedFor(body.apis, body.concept, body.limit, body.offset));
    }),
    http.post(`${base}/v1/model-sets/sessions`, async ({ request }) => {
      const body = (await request.json()) as SetSessionRequest;
      sessionCounter += 1;
      const id = `ss-mock${sessionCounter}`;
      setSessions.set(id, {
        apis: body.apis,
        concepts: body.concepts,
        aliases: body.aliases ?? [],
        setId: null,
      });
      return HttpResponse.json({
        setSessionId: id,
        inputs: body.apis.map((api) => ({ api, build: `b-${api}` })),
        memberSessions: Object.fromEntries(
          body.concepts.map((c) => {
            // a member's own model session: a model draft pasted there is stored like any other
            const member = `s-${id}-${c}`;
            modelSessions.set(member, {
              apis: body.apis,
              concept: c,
              basedOn: null,
              snapshotId: null,
            });
            return [c, member];
          }),
        ),
        contextUrl: `/v1/model-sets/sessions/${id}/context`,
        claudePrompt: `Use the Plume MCP: get_set_context("${id}"), write or reuse a model for each of ${body.concepts.join(', ')}, ask me how each relation should be designed, then submit_model_set("${id}", draft).${
          body.aliases?.length
            ? ` Treat ${body.aliases
                .map((a) =>
                  Object.entries(a.names)
                    .map(([api, n]) => `${api} "${n}"`)
                    .join(' and '),
                )
                .join('; ')} as the same concept.`
            : ''
        }`,
      });
    }),
    http.get(`${base}/v1/model-sets/sessions/:id`, ({ params, request }) => {
      const x = setSessions.get(String(params.id));
      if (!x)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      const stored = x.setId ? sets.get(x.setId) : undefined;
      void request;
      // the server answers snake_case here
      return HttpResponse.json({
        set_session_id: params.id,
        status: x.setId ? 'submitted' : 'open',
        set_id: x.setId,
        visibility: stored?.set.visibility ?? null,
        concepts: x.concepts,
        member_sessions: {},
        based_on: null,
      });
    }),
    // a stand-in for Claude's submit_model_set (tests call it from the page to finish a session)
    http.post(`${base}/v1/model-sets/sessions/:id/draft`, async ({ params, request }) => {
      const x = setSessions.get(String(params.id));
      if (!x)
        return HttpResponse.json(
          { error: 'not_found', message: 'No such session' },
          { status: 404 },
        );
      // Refused like the server does: `refuse: "relation"` (a relation that does not validate) or a bad `members`
      const draft = (await request.json().catch(() => ({}))) as {
        refuse?: unknown;
        members?: unknown;
      };
      if (
        draft.refuse === 'relation' ||
        (draft.members !== undefined && typeof draft.members !== 'object')
      ) {
        const issues = [
          draft.refuse === 'relation'
            ? {
                code: 'RELATION_INVALID',
                field: 'order-items',
                api: null,
                message: 'Order has no field "items" that can hold Product',
              }
            : {
                code: 'INVALID_FORMAT',
                field: 'members',
                api: null,
                message: 'members must map each concept to a stored model id',
              },
        ];
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
      }
      const maintainer = isMaintainer(request);
      const id = maintainer ? `set_mock${sets.size + 1}` : `u-set-mock${sets.size + 1}`;
      const s = newSet(id, x.concepts, x.apis, maintainer ? 'unreleased' : 'unlisted', {
        aliases: x.aliases.map((a) => ({ concept: a.concept, names: a.names })),
      });
      sets.set(id, s);
      x.setId = id;
      return HttpResponse.json(
        {
          created: true,
          visibility: s.set.visibility,
          ownerKey: s.ownerKey ?? null,
          set: setJson(allSets(), s),
        },
        { status: 201 },
      );
    }),
    // server generation of a set: the first concept names the job; `Refund` first = no model key (503),
    // `Customer` among the members = the job fails
    http.post(`${base}/v1/model-sets/generate`, async ({ request }) => {
      if (!isMaintainer(request)) return unauthorized();
      const body = (await request.json()) as SetSessionRequest;
      if (body.concepts[0]?.toLowerCase() === 'refund')
        return HttpResponse.json(
          {
            error: 'llm_unavailable',
            message: 'Server-side generation is not configured on this Plume.',
          },
          { status: 503 },
        );
      jobCounter += 1;
      const jobId = `mj-mockset${jobCounter}`;
      const setId = `set_job${jobCounter}`;
      const { events } = setJobScript(jobId, body.apis, body.concepts, setId);
      modelJobs.set(jobId, {
        events,
        job: {
          jobId,
          kind: 'model_set',
          status: 'queued',
          apis: body.apis,
          concept: body.concepts.join('+'),
          round: 0,
          maxRounds: 3,
          snapshotId: null,
          setId: null,
          error: null,
          createdAt: '2026-11-16T14:00:00Z',
          updatedAt: '2026-11-16T14:00:00Z',
        },
      });
      return HttpResponse.json(
        { jobId, status: 'queued', eventsUrl: `/v1/models/jobs/${jobId}/events` },
        { status: 202 },
      );
    }),
    // ---- model sets: official and unlisted ones are public, unreleased ones need the token (404 otherwise) ----
    http.get(`${base}/v1/model-sets`, ({ request }) => {
      const want = new URL(request.url).searchParams.get('visibility');
      if (want && !isMaintainer(request))
        return HttpResponse.json(
          { error: 'unauthorized', message: 'Missing or invalid token' },
          { status: 401 },
        );
      const all = allSets();
      const vis = want ?? 'official';
      let rows = all.filter((x) => (vis === 'all' ? true : x.set.visibility === vis));
      // the public list shows the latest official version of each lineage
      if (vis === 'official')
        rows = rows.filter(
          (x) => !rows.some((o) => o.lineageId === x.lineageId && o.createdAt > x.createdAt),
        );
      rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
      return HttpResponse.json({ items: rows.map((x) => setListItem(all, x)) });
    }),
    http.post(`${base}/v1/model-sets/mine`, async ({ request }) => {
      const { ownerKeys } = (await request.json()) as { ownerKeys?: string[] };
      const keys = Array.isArray(ownerKeys) ? ownerKeys : [];
      const all = allSets();
      const mine = all
        .filter((x) => x.ownerKey && keys.includes(x.ownerKey) && x.set.visibility !== 'discarded')
        .filter(
          (x, _i, rows) =>
            !rows.some((o) => o.lineageId === x.lineageId && o.createdAt > x.createdAt),
        );
      return HttpResponse.json({ items: mine.map((x) => setListItem(all, x)) });
    }),
    http.get(`${base}/v1/model-sets/:id`, ({ params, request }) => {
      const x = sets.get(String(params.id));
      if (
        !x ||
        ((x.set.visibility === 'unreleased' || x.set.visibility === 'discarded') &&
          !isMaintainer(request))
      )
        return HttpResponse.json(
          { error: 'not_found', message: 'Model set not found' },
          { status: 404 },
        );
      return HttpResponse.json(setJson(allSets(), x));
    }),
    http.post(`${base}/v1/model-sets/:id/release`, ({ params, request }) => {
      if (!isMaintainer(request))
        return HttpResponse.json(
          { error: 'unauthorized', message: 'Missing or invalid token' },
          { status: 401 },
        );
      const x = sets.get(String(params.id));
      if (!x)
        return HttpResponse.json(
          { error: 'not_found', message: 'Model set not found' },
          { status: 404 },
        );
      if (x.set.visibility !== 'unreleased')
        return HttpResponse.json(
          { error: 'invalid_state', message: 'Only an unreleased set can be released.' },
          { status: 409 },
        );
      if (x.set.undecided.length)
        return HttpResponse.json(
          {
            error: 'undecided_relations',
            message: `${x.set.undecided.length} relation(s) are still undecided.`,
          },
          { status: 409 },
        );
      x.set = {
        ...x.set,
        visibility: 'official',
        official: true,
        releasedAt: '2026-11-16T14:00:00Z',
      };
      return HttpResponse.json({
        set: setJson(allSets(), x),
        releasedMembers: x.set.members.filter((m) => !m.missing).map((m) => m.modelId),
      });
    }),
    http.post(`${base}/v1/model-sets/:id/discard`, ({ params, request }) => {
      if (!isMaintainer(request))
        return HttpResponse.json(
          { error: 'unauthorized', message: 'Missing or invalid token' },
          { status: 401 },
        );
      const x = sets.get(String(params.id));
      if (!x)
        return HttpResponse.json(
          { error: 'not_found', message: 'Model set not found' },
          { status: 404 },
        );
      if (x.set.visibility !== 'unreleased')
        return HttpResponse.json(
          { error: 'invalid_state', message: 'Only an unreleased set can be discarded.' },
          { status: 409 },
        );
      x.set = { ...x.set, visibility: 'discarded', official: false };
      return HttpResponse.json(setJson(allSets(), x));
    }),
    // the editor: the chosen design of relations becomes a NEW version of the set
    http.post(`${base}/v1/model-sets/:id/relations`, async ({ params, request }) => {
      if (request.headers.get('authorization') && !isMaintainer(request))
        return HttpResponse.json(
          { error: 'unauthorized', message: 'The token is not valid.' },
          { status: 401 },
        );
      const maintainer = isMaintainer(request);
      const baseSet = sets.get(String(params.id));
      if (
        !baseSet ||
        (baseSet.set.visibility === 'unreleased' && !maintainer) ||
        baseSet.set.visibility === 'discarded'
      )
        return HttpResponse.json(
          { error: 'not_found', message: 'Model set not found' },
          { status: 404 },
        );
      const all = allSets();
      const latest = lineageOfSet(all, baseSet).latestId;
      if (latest !== baseSet.set.id)
        return HttpResponse.json(
          {
            error: 'not_latest',
            message: `This is not the latest version of the set (${latest}).`,
          },
          { status: 409 },
        );
      const body = (await request.json()) as { relations?: RelationEdit[] };
      const result = applyEdits(baseSet.set, body.relations ?? []);
      if ('status' in result)
        return HttpResponse.json(
          {
            error: result.error,
            message: result.message,
            ...(result.issues ? { issues: result.issues } : {}),
          },
          { status: result.status },
        );
      const n = sets.size + 1;
      const fresh = !maintainer && baseSet.set.visibility === 'official'; // the user's own unlisted copy
      const visibility = maintainer
        ? baseSet.set.visibility === 'unlisted'
          ? 'unlisted'
          : 'unreleased'
        : 'unlisted';
      const id = visibility === 'unlisted' ? `u-set${String(n).padStart(23, '0')}` : `set_v${n}`;
      const ownerKey = fresh ? `pk_set_mock${n}` : null;
      const stored: StoredSet = {
        set: {
          ...baseSet.set,
          id,
          visibility,
          official: false,
          releasedAt: null,
          basedOn: baseSet.set.id,
          relations: result.relations,
          undecided: result.relations.filter((r) => !r.confirmed).map((r) => r.id),
          sharePath: `/model-sets/${id}`,
          generatedAt: '2026-11-16T15:00:00Z',
        },
        lineageId: fresh ? `S-${id}` : baseSet.lineageId,
        ownerKey: ownerKey ?? baseSet.ownerKey,
        createdAt: new Date(Date.UTC(2026, 10, 16, 15, 0, sets.size)).toISOString(),
      };
      sets.set(id, stored);
      return HttpResponse.json(
        { created: true, visibility, ownerKey, set: setJson(allSets(), stored) },
        { status: 201 },
      );
    }),
    http.get(`${base}/v1/maintainer/me`, ({ request }) =>
      isMaintainer(request)
        ? HttpResponse.json({ name: 'maintainer', generation: true })
        : unauthorized(),
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
