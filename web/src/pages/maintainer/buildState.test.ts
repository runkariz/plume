import { buildReducer, initialBuildState } from './buildState';

describe('buildReducer', () => {
  it('starts with every step pending', () => {
    const s = initialBuildState();
    expect(Object.values(s.steps).every((x) => x.status === 'pending')).toBe(true);
    expect(s.phase).toBe('connecting');
  });
  it('applies step, progress, service and done events', () => {
    let s = initialBuildState();
    s = buildReducer(s, {
      type: 'step',
      id: '1',
      key: 'embed',
      status: 'running',
      detail: 'Batch 1',
    });
    s = buildReducer(s, { type: 'progress', id: '2', done: 16, total: 50, etaSeconds: 7 });
    s = buildReducer(s, { type: 'service', id: '3', service: 'gemini', detail: 'embedding-001' });
    expect(s.phase).toBe('live');
    expect(s.steps.embed).toEqual({ status: 'running', detail: 'Batch 1' });
    expect(s.progress).toEqual({ done: 16, total: 50, etaSeconds: 7 });
    expect(s.services.gemini).toBe('embedding-001');
    s = buildReducer(s, { type: 'done', id: '4', status: 'staged' });
    expect(s.phase).toBe('staged');
  });
  it('a finished build has no running step left', () => {
    let s = buildReducer(initialBuildState(), {
      type: 'step',
      id: '1',
      key: 'evaluate',
      status: 'running',
      detail: 'x',
    });
    s = buildReducer(s, { type: 'done', id: '2', status: 'staged' });
    expect(s.steps.evaluate.status).toBe('done');
    let f = buildReducer(initialBuildState(), {
      type: 'step',
      id: '1',
      key: 'embed',
      status: 'running',
      detail: 'x',
    });
    f = buildReducer(f, { type: 'done', id: '2', status: 'failed', message: 'boom' });
    expect(f.steps.embed.status).toBe('failed');
    expect(f.message).toBe('boom');
  });
  it('ignores a log line replayed after a reconnect', () => {
    const e = { type: 'log', id: '9', t: '14:00:00', source: 'plume', message: 'x' } as const;
    let s = buildReducer(initialBuildState(), e);
    s = buildReducer(s, e);
    expect(s.logs).toHaveLength(1);
  });
  it('caps the log and records a lost connection', () => {
    let s = initialBuildState();
    for (let i = 0; i < 450; i += 1)
      s = buildReducer(s, { type: 'log', id: String(i), t: 't', source: 'gemini', message: 'm' });
    expect(s.logs).toHaveLength(400);
    s = buildReducer(s, { type: 'lost', message: 'offline' });
    expect(s.phase).toBe('lost');
    expect(s.message).toBe('offline');
  });
});
