import { http, HttpResponse } from 'msw';
import { apiBaseUrl } from '@/api/config';
import type { CheckCallRequest, ItemKind, SearchRequest } from '@/api/types';
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

export function createHandlers(base: string = apiBaseUrl()) {
  return [
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
