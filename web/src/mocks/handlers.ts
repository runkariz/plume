import { delay, http, HttpResponse } from 'msw';
import { apiBaseUrl } from '@/api/config';
import type {
  CheckCallRequest,
  GenerateRequest,
  ItemKind,
  Job,
  ReviewRequest,
  SearchRequest,
} from '@/api/types';
import { apiRef, modelCandidates, sampleSuggestions, snapshots } from './modelData';
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

const unauthorized = () =>
  HttpResponse.json({ detail: 'Invalid or missing token' }, { status: 401 });
const isMaintainer = (req: Request) =>
  (req.headers.get('authorization') ?? '').startsWith('Bearer pl_');

export function createHandlers(base: string = apiBaseUrl(), opts: MockOptions = {}) {
  const eventDelay = opts.eventDelayMs ?? 0;
  /** In-memory job store: one sample job per upload, advanced by the endpoints below. */
  const jobs = new Map<string, Job>();
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
    http.post(`${base}/v1/models/generate`, async ({ request }) => {
      const body = (await request.json()) as GenerateRequest;
      const snapshotId = body.concept === 'inventory' ? 'snap_8f3a21' : 'snap_prod01';
      return HttpResponse.json({ snapshotId });
    }),
    http.get(`${base}/v1/models/:id`, ({ params }) => {
      const snap = snapshots[String(params.id)];
      return snap
        ? HttpResponse.json(snap)
        : HttpResponse.json({ detail: 'Snapshot not found' }, { status: 404 });
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
        headers: { 'Content-Type': 'application/gzip' },
      });
    }),
    http.get(`${base}/v1/apis`, () => HttpResponse.json({ items: sampleApis })),
    http.get(`${base}/v1/apis/:id`, ({ params }) => {
      const found = detailFor(String(params.id));
      return found ? HttpResponse.json(found) : notFound();
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
