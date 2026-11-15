import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ModelJobEvent } from '@/api/types';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { BeatLine, beatText, JobClock } from './JobClock';
import { reduce } from './ModelJobProgress';

const EMPTY = {
  documents: null,
  fields: null,
  rounds: [],
  maxRounds: 3,
  snapshotId: null,
  failure: null,
  finished: false,
  beat: null,
  repairs: [],
};

/** A job stream that stays open: the events as the server sends them while a model call is in flight. */
function openStream(events: { event: string; data: object }[]) {
  const enc = new TextEncoder();
  return new HttpResponse(
    new ReadableStream({
      start(c) {
        events.forEach((e, i) =>
          c.enqueue(
            enc.encode(`id: ${i + 1}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`),
          ),
        );
        // never closed: the job is still running
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

beforeEach(() => server.use(...createHandlers(TEST_API_BASE)));
afterEach(() => authStore.signOut());

describe('the heartbeat of a generation job', () => {
  it('is kept by the reducer (the latest one), and an event nobody knows leaves the state as it was', () => {
    const t0 = Date.now();
    let p = reduce(EMPTY, { type: 'heartbeat', elapsed: 12, round: 1, phase: 'waiting_for_model' });
    expect(p.beat).toMatchObject({ seconds: 12, round: 1, phase: 'waiting_for_model' });
    expect(p.beat?.at).toBeGreaterThanOrEqual(t0);
    p = reduce(p, { type: 'heartbeat', elapsed: 27, round: 1, phase: 'waiting_for_model' });
    expect(p.beat?.seconds).toBe(27);
    const before = p;
    expect(reduce(p, { type: 'something-new' } as unknown as ModelJobEvent)).toEqual(before);
  });

  it('says what the server waits for, with its clock and the round', () => {
    expect(beatText({ seconds: 1, at: 0, phase: 'waiting_for_model' })).toBe(
      'Waiting for the model',
    );
    expect(beatText({ seconds: 1, at: 0, phase: 'validating' })).toBe('Checking the draft');
    expect(beatText({ seconds: 1, at: 0, phase: 'some_new_phase' })).toBe('some new phase');
    expect(beatText({ seconds: 1, at: 0, phase: 'x', detail: 'Retrying after a 429' })).toBe(
      'Retrying after a 429',
    );
    expect(beatText({ seconds: 1, at: 0 })).toBe('Working');
    render(
      <BeatLine
        beat={{ seconds: 161, at: 0, round: 2, phase: 'waiting_for_model' }}
        maxRounds={3}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Waiting for the model, 2:41 (round 2 of 3)',
    );
  });

  it('shows nothing before the first heartbeat', () => {
    const { container } = render(<BeatLine beat={null} maxRounds={3} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('the badge shows a clock that keeps going between heartbeats', () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    try {
      render(<JobClock running beat={{ seconds: 161, at: Date.now() }} />);
      expect(screen.getByText('2:41')).toBeInTheDocument();
      act(() => void vi.advanceTimersByTime(3000));
      expect(screen.getByText('2:44')).toBeInTheDocument();
      // the ticking badge is not a live region: it would be announced every second
      expect(screen.getByText(/Working on the server/).closest('[aria-live]')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('on the page: a long model call shows "Waiting for the model" and a running clock, then the result', async () => {
    authStore.signIn('pl_ok', 'maintainer', true);
    server.use(
      http.get(`${TEST_API_BASE}/v1/models/jobs/:id/events`, () =>
        openStream([
          {
            event: 'started',
            data: { apis: ['shopify', 'woocommerce', 'mirakl'], concept: 'shipment' },
          },
          { event: 'round', data: { n: 2, of: 3 } },
          { event: 'heartbeat', data: { elapsed: 161, round: 2, phase: 'waiting_for_model' } },
        ]),
      ),
    );
    renderApp('/models/suggest?apis=shopify,woocommerce,mirakl');
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Shipment' }));
    const panel = await screen.findByRole('region', { name: 'Generation on the server' });
    expect(
      await within(panel).findByText('Waiting for the model, 2:41 (round 2 of 3)'),
    ).toBeInTheDocument();
    expect(within(panel).getByText(/Working on the server/)).toBeInTheDocument();
    expect(within(panel).getByText(/^2:4\d$/)).toBeInTheDocument();
  });
});
