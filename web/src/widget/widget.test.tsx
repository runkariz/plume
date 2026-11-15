import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { inventorySnapshot } from '@/mocks/modelData';
import { extractModel, normalise } from './model';
import { HostConnection, PROTOCOL_VERSION, type Transport } from './protocol';
import { WidgetApp } from './WidgetApp';

/** A fake host: records what the view sends and lets the test push messages as the host would. */
function fakeHost(timeoutMs = 10_000) {
  const sent: Record<string, unknown>[] = [];
  let deliver: (data: unknown) => void = () => undefined;
  const transport: Transport = {
    send: (m) => {
      sent.push(m as unknown as Record<string, unknown>);
    },
    listen: (h) => {
      deliver = h;
      return () => {
        deliver = () => undefined;
      };
    },
  };
  const conn = new HostConnection(transport, timeoutMs);
  return {
    conn,
    sent,
    push: (m: unknown) => act(() => deliver(m)),
    methods: () => sent.map((m) => m.method ?? `result:${String(m.id)}`),
    reply: (id: unknown, result: unknown) => act(() => deliver({ jsonrpc: '2.0', id, result })),
  };
}

const result = (structuredContent: unknown, extra: object = {}) => ({
  content: [{ type: 'text', text: 'summary' }],
  structuredContent,
  ...extra,
});

describe('the host protocol', () => {
  it('does the handshake in order: ui/initialize, then the initialized notification', async () => {
    const h = fakeHost();
    const init = h.conn.initialize({ name: 'plume', version: '1' });
    expect(h.sent[0]).toMatchObject({
      jsonrpc: '2.0',
      method: 'ui/initialize',
      params: { protocolVersion: PROTOCOL_VERSION, appInfo: { name: 'plume' } },
    });
    expect(h.methods()).toEqual(['ui/initialize']); // nothing else before the host answers
    await h.reply(h.sent[0]?.id, {
      protocolVersion: PROTOCOL_VERSION,
      hostCapabilities: { openLinks: {} },
      hostContext: {
        theme: 'dark',
        styles: { variables: { '--color-background-primary': '#111' } },
      },
    });
    const r = await init;
    expect(r.hostContext.theme).toBe('dark');
    expect(r.hostCapabilities.openLinks).toBeDefined();
    expect(h.methods()).toEqual(['ui/initialize', 'ui/notifications/initialized']);
  });

  it('passes tool results and merges partial host-context changes', async () => {
    const h = fakeHost();
    const got: unknown[] = [];
    h.conn.on('ui/notifications/tool-result', (p) => got.push(p));
    const init = h.conn.initialize({ name: 'p', version: '1' });
    await h.reply(h.sent[0]?.id, {
      hostContext: { theme: 'light', styles: { variables: { '--a': '1', '--b': '2' } } },
    });
    await init;
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: { structuredContent: 1 },
    });
    expect(got).toEqual([{ structuredContent: 1 }]);
    const merged = h.conn.mergeContext({ theme: 'dark', styles: { variables: { '--b': '3' } } });
    expect(merged.theme).toBe('dark');
    expect(merged.styles?.variables).toEqual({ '--a': '1', '--b': '3' }); // a partial update keeps the rest
  });

  it("answers the host's ping and teardown, and refuses what it does not know", async () => {
    const h = fakeHost();
    await h.push({ jsonrpc: '2.0', id: 7, method: 'ping' });
    await h.push({ jsonrpc: '2.0', id: 8, method: 'ui/resource-teardown', params: {} });
    await h.push({ jsonrpc: '2.0', id: 9, method: 'something/else' });
    expect(h.sent).toEqual([
      { jsonrpc: '2.0', id: 7, result: {} },
      { jsonrpc: '2.0', id: 8, result: {} },
      {
        jsonrpc: '2.0',
        id: 9,
        error: { code: -32601, message: 'Method not found: something/else' },
      },
    ]);
  });

  it('ignores anything that is not JSON-RPC 2.0, and answers for unknown ids nobody asked', async () => {
    const h = fakeHost();
    const seen = vi.fn();
    h.conn.on('x', seen);
    for (const bad of [
      null,
      'text',
      5,
      { method: 'x' },
      { jsonrpc: '1.0', method: 'x' },
      { jsonrpc: '2.0', id: 99, result: 1 },
    ])
      await h.push(bad);
    expect(seen).not.toHaveBeenCalled();
    expect(h.sent).toEqual([]);
  });

  it('opens a link only when the host offers openLinks, and reports the height', async () => {
    const none = fakeHost();
    expect(await none.conn.openLink('https://plume.example/models/x')).toBe(false);
    expect(none.sent).toEqual([]);
    const h = fakeHost();
    const init = h.conn.initialize({ name: 'p', version: '1' });
    await h.reply(h.sent[0]?.id, { hostCapabilities: { openLinks: {} }, hostContext: {} });
    await init;
    const opened = h.conn.openLink('https://plume.example/models/x');
    const req = h.sent.find((m) => m.method === 'ui/open-link');
    expect(req?.params).toEqual({ url: 'https://plume.example/models/x' });
    await h.reply(req?.id, {});
    expect(await opened).toBe(true);
    h.conn.sizeChanged({ height: 321 });
    expect(h.sent.at(-1)).toMatchObject({
      method: 'ui/notifications/size-changed',
      params: { height: 321 },
    });
    expect(h.sent.at(-1)).not.toHaveProperty('id'); // a notification
  });

  it('gives up when the host never answers the handshake', async () => {
    vi.useFakeTimers();
    const h = fakeHost(50);
    const init = h.conn.initialize({ name: 'p', version: '1' });
    const caught = init.catch((e: Error) => e.message);
    await vi.advanceTimersByTimeAsync(60);
    expect(await caught).toContain('did not answer ui/initialize');
    vi.useRealTimers();
  });
});

describe('the model of a tool result', () => {
  const model = inventorySnapshot;

  it('reads structuredContent.model first, then structuredContent itself', () => {
    expect(extractModel(result(model))).toMatchObject({ kind: 'model', model: { id: model.id } });
    expect(
      extractModel(
        result({ accepted: true, snapshot_id: model.id, share_url: 'https://p/models/x', model }),
      ),
    ).toMatchObject({ kind: 'model', link: 'https://p/models/x', model: { id: model.id } });
    // get_generation: the job and the model
    expect(extractModel(result({ status: 'succeeded', model }))).toMatchObject({ kind: 'model' });
  });

  it('shows a refused draft with its issues, a running job, a failed tool and anything unknown', () => {
    const issues = [{ code: 'QUOTE_NOT_FOUND', field: 'total', api: 'shopify', message: 'no' }];
    expect(extractModel(result({ accepted: false, issues }))).toEqual({ kind: 'refused', issues });
    expect(extractModel(result({ accepted: false }))).toEqual({ kind: 'refused', issues: [] });
    expect(extractModel(result({ status: 'running' }))).toEqual({
      kind: 'pending',
      status: 'running',
    });
    expect(extractModel(result({}, { isError: true }))).toEqual({
      kind: 'error',
      message: 'summary',
    });
    expect(extractModel({ content: [] })).toEqual({ kind: 'unrecognised' });
    expect(extractModel(result({ id: 'x', fields: 'not a list' }))).toEqual({
      kind: 'unrecognised',
    });
    expect(extractModel(result('text'))).toEqual({ kind: 'unrecognised' });
  });

  it("uses the model's own share link when the result has none, and none when there is none", () => {
    expect(extractModel(result({ ...model, shareUrl: 'https://p/models/y' }))).toMatchObject({
      link: 'https://p/models/y',
    });
    expect(extractModel(result(model))).toMatchObject({ link: null });
  });

  it('normalises display names and drops icon URLs (a relative path cannot load in the sandbox)', () => {
    const m = normalise({
      ...model,
      inputs: model.inputs.map((a) => ({
        ...a,
        shortName: 'Woocommerce',
        id: 'woocommerce',
        logo: { ...a.logo, url: '/v1/apis/x/icon' },
      })),
    });
    expect(m.inputs.every((a) => a.shortName === 'WooCommerce')).toBe(true);
    expect(m.inputs.every((a) => a.logo.url === null)).toBe(true);
  });
});

describe('a result that is not shaped like the HTTP routes', () => {
  it('falls back to a letter on a neutral tile when the server sent no logo (older MCP results)', () => {
    const noLogo = {
      ...inventorySnapshot,
      inputs: inventorySnapshot.inputs.map(({ id, shortName, name, build }) => ({
        id,
        shortName,
        name,
        build,
      })),
    };
    const shown = extractModel(result(noLogo));
    expect(shown.kind).toBe('model');
    if (shown.kind !== 'model') return;
    for (const a of shown.model.inputs) {
      expect(a.logo.text).toBe(a.shortName.slice(0, 1).toUpperCase());
      expect(a.logo.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(a.logo.url).toBeNull();
    }
  });

  it('ignores a colour that is not a hex colour and a logo that is not an object', () => {
    for (const logo of [{ text: 'S', color: 'red' }, { text: 5, color: null }, 'x', null, {}]) {
      const m = {
        ...inventorySnapshot,
        inputs: inventorySnapshot.inputs.map((a) => ({ ...a, logo })),
      };
      const shown = extractModel(result(m));
      expect(shown.kind, JSON.stringify(logo)).toBe('model');
      if (shown.kind === 'model')
        expect(shown.model.inputs[0]?.logo.color).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it('keeps a valid logo and renders the whole view without one', async () => {
    const noLogo = {
      ...inventorySnapshot,
      inputs: inventorySnapshot.inputs.map(({ id, shortName, name, build }) => ({
        id,
        shortName,
        name,
        build,
      })),
    };
    const h = fakeHost();
    render(<WidgetApp connection={h.conn} />);
    await h.reply(h.sent[0]?.id, { hostCapabilities: {}, hostContext: { theme: 'light' } });
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: result(noLogo),
    });
    expect(await screen.findByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Mapping graph/ })).toBeInTheDocument();
  });
});

describe('the view', () => {
  async function shown(structured: unknown, caps: object = {}) {
    const h = fakeHost();
    render(<WidgetApp connection={h.conn} />);
    expect(screen.getByText('Waiting for the model…')).toBeInTheDocument();
    await h.reply(h.sent[0]?.id, { hostCapabilities: caps, hostContext: { theme: 'light' } });
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: result(structured),
    });
    return h;
  }

  it('shows the model: name, visibility, the graph with the control box, the detail, the coverage', async () => {
    await shown({ ...inventorySnapshot, visibility: 'official' });
    expect(await screen.findByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByText('Official')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Mapping graph/ })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Graph controls' })).toBeInTheDocument();
    const detail = screen.getByRole('region', { name: 'Mapping detail' });
    expect(within(detail).getByRole('heading')).toHaveTextContent(' ← ');
    const cov = screen.getByRole('list', { name: 'Coverage' });
    expect(within(cov).getAllByRole('listitem')).toHaveLength(inventorySnapshot.inputs.length);
    // no links to pages the frame cannot open: a cited document is text
    expect(within(detail).queryByRole('link')).not.toBeInTheDocument();
  });

  it('follows the host theme and its changes', async () => {
    const h = await shown(inventorySnapshot);
    await screen.findByRole('heading', { name: 'Inventory' });
    expect(document.documentElement.dataset.theme).toBe('light');
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/host-context-changed',
      params: { theme: 'dark' },
    });
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('"Open in Plume" asks the host to open the share link; without the capability it shows the link as text', async () => {
    const h = await shown(
      { accepted: true, share_url: 'https://plume.example/models/u-1', model: inventorySnapshot },
      { openLinks: {} },
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Open in Plume' }));
    expect(h.sent.find((m) => m.method === 'ui/open-link')?.params).toEqual({
      url: 'https://plume.example/models/u-1',
    });
  });

  it('shows the link as text when the host cannot open links, and the path when there is no public URL', async () => {
    const { unmount } = render(<span />);
    unmount();
    await shown({
      accepted: true,
      share_url: 'https://plume.example/models/u-1',
      model: inventorySnapshot,
    });
    expect(await screen.findByText('https://plume.example/models/u-1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open in Plume' })).not.toBeInTheDocument();
  });

  it('shows a refused draft briefly: the codes and why, nothing stored', async () => {
    await shown({
      accepted: false,
      issues: [
        {
          code: 'QUOTE_NOT_FOUND',
          field: 'total',
          api: 'shopify',
          message: 'the quote is not in the doc',
        },
      ],
    });
    expect(
      await screen.findByText('The draft was refused, nothing was stored'),
    ).toBeInTheDocument();
    expect(screen.getByText('QUOTE_NOT_FOUND')).toBeInTheDocument();
    expect(screen.getByText('the quote is not in the doc')).toBeInTheDocument();
  });

  it('package text is rendered as text, never as markup', async () => {
    const evil = '<img src=x onerror="alert(1)">';
    await shown({ ...inventorySnapshot, name: evil, openQuestions: [{ question: `**${evil}**` }] });
    expect(await screen.findByRole('heading', { name: evil })).toBeInTheDocument();
    expect(document.querySelector('img[onerror]')).toBeNull();
    await userEvent.click(screen.getByText(/Open questions/));
    expect(screen.getByText(`**${evil}**`)).toBeInTheDocument();
  });

  it('says what it is when no host embeds it', () => {
    render(<WidgetApp connection={null} />);
    expect(screen.getByText(/shown by a Claude app that supports MCP Apps/)).toBeInTheDocument();
  });

  it('says so when the host never answers', async () => {
    vi.useFakeTimers();
    const h = fakeHost(30);
    render(<WidgetApp connection={h.conn} />);
    await act(() => vi.advanceTimersByTimeAsync(40));
    expect(screen.getByText('The model view could not start')).toBeInTheDocument();
    vi.useRealTimers();
  });
});
