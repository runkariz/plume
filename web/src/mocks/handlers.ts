import { http, HttpResponse } from 'msw';
import { apiBaseUrl } from '@/api/config';
import { sampleApis } from './data';

export function createHandlers(base: string = apiBaseUrl()) {
  return [
    http.get(`${base}/v1/apis`, () => HttpResponse.json({ items: sampleApis })),
    http.get(`${base}/v1/apis/:id`, ({ params }) => {
      const found = sampleApis.find((a) => a.id === params.id);
      return found
        ? HttpResponse.json(found)
        : HttpResponse.json({ detail: 'API not found' }, { status: 404 });
    }),
  ];
}
