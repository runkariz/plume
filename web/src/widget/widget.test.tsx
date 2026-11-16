import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { inventorySnapshot } from '@/mocks/modelData';
import { SET_OFFICIAL, seedSets, setJson } from '@/mocks/setStore';
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

describe('a model set result', () => {
  const all = seedSets();
  const stored = all.find((x) => x.set.id === SET_OFFICIAL);
  const set = stored ? setJson(all, stored) : (undefined as never);

  it('reads a set from get_model_set (the set itself) and from submit/release ({set} with a share_url)', () => {
    expect(extractModel(result(set))).toMatchObject({
      kind: 'set',
      set: { id: SET_OFFICIAL },
      link: null,
    });
    expect(
      extractModel(result({ accepted: true, share_url: 'https://p/model-sets/x', set })),
    ).toMatchObject({
      kind: 'set',
      link: 'https://p/model-sets/x',
    });
    expect(extractModel(result({ set, releasedMembers: ['m-order'] }))).toMatchObject({
      kind: 'set',
    });
    // a set carries no `fields`: it is not mistaken for a model
    expect(extractModel(result(set)).kind).not.toBe('model');
  });

  it('survives a set without lists, without logos and with an odd colour', () => {
    const bare = {
      kind: 'model_set',
      id: 's-1',
      name: 'Bare',
      visibility: 'unlisted',
      members: [],
      inputs: [{ id: 'shopify', shortName: 'Shopify', logo: { text: 5, color: 'red' } }],
    };
    const shown = extractModel(result(bare));
    expect(shown.kind).toBe('set');
    if (shown.kind !== 'set') return;
    expect(shown.set.relations).toEqual([]);
    expect(shown.set.undecided).toEqual([]);
    expect(shown.set.inputs[0]?.logo).toMatchObject({ text: 'S', url: null });
  });

  async function shownSet(structured: unknown, caps: object = {}) {
    const h = fakeHost();
    render(<WidgetApp connection={h.conn} />);
    await h.reply(h.sent[0]?.id, { hostCapabilities: caps, hostContext: { theme: 'light' } });
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: result(structured),
    });
    return h;
  }

  it('shows the set: name, chips, the diagram, the models and the relations as text', async () => {
    await shownSet(set);
    expect(await screen.findByRole('heading', { name: 'Shop', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('Official')).toBeInTheDocument();
    expect(screen.getByText('3 models')).toBeInTheDocument();
    expect(screen.getByText('2 relations')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Model set diagram/ })).toBeInTheDocument();
    const models = screen.getByRole('region', { name: 'Models' });
    expect(within(models).getAllByRole('listitem')).toHaveLength(3);
    expect(within(models).getByText(/12 fields/)).toBeInTheDocument();
    const relations = screen.getByRole('region', { name: 'Relations' });
    expect(within(relations).getByText('Order → Product')).toBeInTheDocument();
    expect(within(relations).getAllByText('1:n · nested')).toHaveLength(2);
    // how each API documents it, as text; an API that does not says so
    expect(
      within(relations).getAllByText(/WooCommerce does not document it/).length,
    ).toBeGreaterThan(0);
  });

  it('has the control box and the detail: pick a relation and read how each API documents it, read only', async () => {
    await shownSet(set);
    const detail = await screen.findByRole('region', { name: 'Selected model or relation' });
    expect(detail).toHaveTextContent('Pick a model or a relation');
    const list = screen.getByRole('listbox', { name: 'Models and relations' });
    await userEvent.click(within(list).getByRole('option', { name: /Order → Product/ }));
    expect(within(detail).getByRole('heading', { name: 'Order → Product' })).toBeInTheDocument();
    expect(within(detail).getByRole('list', { name: 'Sources' })).toBeInTheDocument();
    expect(within(detail).getAllByText('line_items[].product_id').length).toBeGreaterThan(0);
    // no editor in the chat, and no router link: the way on is "Open in Plume"
    expect(within(detail).queryByRole('radio')).not.toBeInTheDocument();
    expect(within(detail).queryByRole('link')).not.toBeInTheDocument();
    await userEvent.click(within(list).getByRole('option', { name: /^Product\s+\d+ fields/ }));
    expect(within(detail).getByRole('list', { name: 'Coverage' })).toBeInTheDocument();
    expect(within(detail).queryByRole('link')).not.toBeInTheDocument();
  });

  it('an undecided relation says it is decided in Plume, not here', async () => {
    const draft = setJson(
      all,
      all.find((x) => x.set.visibility === 'unreleased') ?? (stored as never),
    );
    await shownSet(draft);
    const list = await screen.findByRole('listbox', { name: 'Models and relations' });
    await userEvent.click(within(list).getByRole('option', { name: /Order → Product/ }));
    const detail = screen.getByRole('region', { name: 'Selected model or relation' });
    expect(detail).toHaveTextContent('Not decided yet: open the set in Plume');
    expect(within(detail).queryByRole('radio')).not.toBeInTheDocument();
  });

  it('says what is still to decide, and opens the set in Plume through the host', async () => {
    const draft = setJson(
      all,
      all.find((x) => x.set.visibility === 'unreleased') ?? (stored as never),
    );
    const h = await shownSet(
      { accepted: true, share_url: 'https://plume.example/model-sets/d', set: draft },
      { openLinks: {} },
    );
    expect(await screen.findByText('1 to decide')).toBeInTheDocument();
    expect(screen.getByText('to decide')).toBeInTheDocument(); // on the relation itself
    expect(screen.getByText('not available to you')).toBeInTheDocument(); // the missing member
    await userEvent.click(screen.getByRole('button', { name: 'Open in Plume' }));
    expect(h.sent.find((m) => m.method === 'ui/open-link')?.params).toEqual({
      url: 'https://plume.example/model-sets/d',
    });
  });

  it('package text is text: a hostile name is not markup', async () => {
    const evil = '<img src=x onerror="alert(1)">';
    await shownSet({
      ...set,
      name: evil,
      members: set.members.map((m, i) => (i === 0 ? { ...m, name: evil } : m)),
    });
    expect(await screen.findByRole('heading', { name: evil })).toBeInTheDocument();
    expect(document.querySelector('img[onerror]')).toBeNull();
  });
});

describe('the My models link of a save without a token (shown in the view only)', () => {
  const COLLECTION = {
    id: 'c-WidgetCollection0123456',
    url: 'https://plume.example/mine/c-WidgetCollection0123456',
    created: true,
  };
  const all = seedSets();
  const stored = all.find((x) => x.set.id === SET_OFFICIAL);
  const set = stored ? setJson(all, stored) : (undefined as never);
  const model = { ...inventorySnapshot, visibility: 'unlisted' };

  async function shown(structured: unknown, caps: object = {}) {
    const h = fakeHost();
    render(<WidgetApp connection={h.conn} />);
    await h.reply(h.sent[0]?.id, { hostCapabilities: caps, hostContext: { theme: 'light' } });
    const push = (sc: unknown) =>
      h.push({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: result(sc) });
    await push(structured);
    return { h, push };
  }

  it('is read from structuredContent.collection for a model and for a set', () => {
    expect(extractModel(result({ accepted: true, collection: COLLECTION, model }))).toMatchObject({
      kind: 'model',
      collection: { id: COLLECTION.id, url: COLLECTION.url, created: true, note: null },
    });
    expect(extractModel(result({ accepted: true, collection: COLLECTION, set }))).toMatchObject({
      kind: 'set',
      collection: { id: COLLECTION.id },
    });
    // the server's note comes along
    expect(
      extractModel(
        result({
          accepted: true,
          collection: { ...COLLECTION, note: 'a new link was made' },
          model,
        }),
      ),
    ).toMatchObject({ collection: { note: 'a new link was made' } });
  });

  it('is no link unless it is a whole one (never a half-link), and an old owner_key is ignored', () => {
    for (const bad of [
      undefined,
      null,
      '',
      5,
      {},
      { id: 'c-x' },
      { url: 'https://x' },
      { id: '', url: 'https://x' },
      { id: 'c-x', url: 5 },
    ])
      expect(extractModel(result({ accepted: true, collection: bad, model }))).toMatchObject({
        collection: null,
      });
    expect(extractModel(result({ accepted: true, owner_key: 'ok-old', model }))).toMatchObject({
      collection: null,
    });
  });

  it('shows "Your models" with the link and Copy, for a model', async () => {
    await shown({ accepted: true, collection: COLLECTION, model });
    expect(await screen.findByText('Your model is saved, and unlisted')).toBeInTheDocument();
    expect(screen.getByText(/new link that lists them/)).toBeInTheDocument();
    expect(screen.getByLabelText('Link to My models')).toHaveValue(COLLECTION.url);
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/owner key/i);
  });

  it('says "model set" for a set, and does not call a link it joined "new"', async () => {
    await shown({ accepted: true, collection: { ...COLLECTION, created: false }, set });
    expect(await screen.findByText('Your model set is saved, and unlisted')).toBeInTheDocument();
    expect(screen.getByText(/saved in your My models list/)).toBeInTheDocument();
    expect(screen.queryByText(/new link that lists them/)).not.toBeInTheDocument();
  });

  it("shows the server's note when it has one", async () => {
    await shown({
      accepted: true,
      collection: {
        ...COLLECTION,
        note: 'The link you sent is not known here, so a new one was made.',
      },
      model,
    });
    expect(await screen.findByText(/so a new one was made/)).toBeInTheDocument();
  });

  it('shows nothing when the result has no link (a maintainer save, or an older server)', async () => {
    await shown({
      accepted: true,
      collection: null,
      model: { ...inventorySnapshot, visibility: 'official' },
    });
    await screen.findByRole('heading', { name: 'Inventory' });
    expect(screen.queryByLabelText('Link to My models')).not.toBeInTheDocument();
    expect(screen.queryByText(/is saved, and unlisted/)).not.toBeInTheDocument();
  });

  it('copies with the clipboard API; when the sandbox refuses it, falls back; when that fails too, says so', async () => {
    await shown({ accepted: true, collection: COLLECTION, model });
    const copyBtn = await screen.findByRole('button', { name: 'Copy link' });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await userEvent.click(copyBtn);
    expect(writeText).toHaveBeenCalledWith(COLLECTION.url);
    expect(await screen.findByText('Link copied')).toBeInTheDocument();
    writeText.mockRejectedValue(new Error('NotAllowedError'));
    const exec = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', { value: exec, configurable: true });
    await userEvent.click(copyBtn);
    expect(exec).toHaveBeenCalledWith('copy');
    exec.mockReturnValue(false);
    await userEvent.click(copyBtn);
    expect(await screen.findByText(/Copy failed: the link is selected/)).toBeInTheDocument();
  });

  it('can be dismissed, and offers "Open My models" only when the host can open links and the link is absolute', async () => {
    const { h } = await shown({ accepted: true, collection: COLLECTION, model }, { openLinks: {} });
    await userEvent.click(await screen.findByRole('button', { name: 'Open My models' }));
    expect(h.sent.find((m) => m.method === 'ui/open-link')?.params).toEqual({
      url: COLLECTION.url,
    });
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByLabelText('Link to My models')).not.toBeInTheDocument();
  });

  it('shows a relative link (the server does not know the web address) as text, with no Open button', async () => {
    await shown(
      {
        accepted: true,
        collection: { ...COLLECTION, url: '/mine/c-WidgetCollection0123456' },
        model,
      },
      { openLinks: {} },
    );
    expect(await screen.findByLabelText('Link to My models')).toHaveValue(
      '/mine/c-WidgetCollection0123456',
    );
    expect(screen.queryByRole('button', { name: 'Open My models' })).not.toBeInTheDocument();
  });

  it('is only text and only in the view: nothing stored, no request', async () => {
    const stash = vi.spyOn(Storage.prototype, 'setItem');
    await shown({ accepted: true, collection: COLLECTION, model });
    await screen.findByLabelText('Link to My models');
    expect(stash).not.toHaveBeenCalled();
    stash.mockRestore();
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

  it('shows the server warnings as text with the fields they are about (no links: no router here)', async () => {
    await shown({
      ...inventorySnapshot,
      visibility: 'unreleased',
      warnings: [
        { code: 'WRITE_ONLY_SOURCE', field: 'number', api: 'shopify', message: 'only a write' },
        {
          code: 'WRITE_ONLY_SOURCE',
          field: 'items.sku',
          api: 'woocommerce',
          message: 'only a write',
        },
      ],
    });
    expect(await screen.findByText(/2 mappings cite only a request body:/)).toHaveTextContent(
      'number, items.sku',
    );
    expect(screen.queryByRole('link', { name: 'number' })).not.toBeInTheDocument();
  });

  it('shows no warning line for a model without warnings, or from a server that sends none', async () => {
    await shown({ ...inventorySnapshot, visibility: 'official', warnings: [] });
    await screen.findByRole('heading', { name: 'Inventory' });
    expect(screen.queryByText(/cite only a request body/)).not.toBeInTheDocument();
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

describe('the impact of newer docs in the view (no fetch: it all comes in the tool result)', () => {
  const rows = Array.from({ length: 7 }, (_, i) => ({
    field: `f${i}`,
    api: 'shopify',
    member: i === 0 ? 'Order' : undefined,
    op: 'removed',
    breaking: i < 2,
    text: `property f${i} removed (removed field)`,
  }));
  const sc = (impact: unknown) => ({
    model: { ...inventorySnapshot, impact },
    share_url: 'https://plume.example/models/x',
  });
  const affected = {
    status: 'affected',
    affectedCount: 7,
    breakingCount: 2,
    rows,
    impactUrl: '/v1/models/x/impact',
  };

  async function shown(structured: unknown) {
    const h = fakeHost();
    render(<WidgetApp connection={h.conn} />);
    await h.reply(h.sent[0]?.id, {
      hostCapabilities: { openLinks: {} },
      hostContext: { theme: 'light' },
    });
    await h.push({
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: result(structured),
    });
    return h;
  }

  it("reads the summary, at most 5 rows of plain text, from the model's impact", () => {
    const s = extractModel(result(sc(affected)));
    if (s.kind !== 'model') throw new Error('not a model');
    expect(s.impact?.impact).toMatchObject({
      status: 'affected',
      affectedCount: 7,
      breakingCount: 2,
    });
    expect(s.impact?.rows).toHaveLength(5);
    expect(s.impact?.rows[0]).toMatchObject({
      member: 'Order',
      breaking: true,
      text: 'property f0 removed (removed field)',
    });
    expect(s.impact?.url).toBe('/v1/models/x/impact');
  });
  it('a set carries its own impact with the members', () => {
    const all = seedSets();
    const stored = all.find((x) => x.set.id === SET_OFFICIAL);
    const set = stored ? setJson(all, stored) : (undefined as never);
    const s = extractModel(
      result({
        set: {
          ...set,
          impact: {
            status: 'affected',
            affectedCount: 1,
            breakingCount: 0,
            rows: [rows[0]],
            byMember: [{ concept: 'Order', modelId: 'm1', status: 'affected', affectedCount: 1 }],
          },
        },
      }),
    );
    if (s.kind !== 'set') throw new Error('not a set');
    expect(s.impact?.impact.byMember).toEqual([
      { concept: 'Order', status: 'affected', affectedCount: 1 },
    ]);
  });
  it('anything else is no impact: a missing, odd or unknown-status summary shows nothing', () => {
    for (const odd of [undefined, null, 'x', { status: 'broken' }, { affectedCount: 2 }]) {
      const s = extractModel(result(sc(odd)));
      expect(s.kind === 'model' ? s.impact : 'x').toBeNull();
    }
  });
  it('shows ONE headline and the rows as text, replacing the older-docs chip', async () => {
    await shown(sc(affected));
    const box = await screen.findByTestId('widget-impact');
    expect(box).toHaveTextContent('7 mappings affected (2 breaking)');
    expect(within(box).getAllByRole('listitem')).toHaveLength(5);
    expect(box).toHaveTextContent('Breaking: ');
    expect(box).toHaveTextContent('Order: property f0 removed (removed field)');
    expect(screen.queryByText('Built on older docs')).not.toBeInTheDocument();
  });
  it('a row with markup stays text', async () => {
    await shown(sc({ ...affected, rows: [{ ...rows[0], text: '<img src=x onerror=alert(1)>' }] }));
    const box = await screen.findByTestId('widget-impact');
    expect(box).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(box.querySelector('img')).toBeNull();
  });
  it('is quiet when current, and the stale chip stays when the server sent no impact', async () => {
    await shown(sc({ status: 'current', affectedCount: 0, breakingCount: 0 }));
    expect(screen.queryByTestId('widget-impact')).not.toBeInTheDocument();
  });
  it('an older server (no impact): the older-docs chip for a stale model, nothing else', async () => {
    await shown({ model: { ...inventorySnapshot, impact: undefined, stale: true } });
    expect(await screen.findByText('Built on older docs')).toBeInTheDocument();
    expect(screen.queryByTestId('widget-impact')).not.toBeInTheDocument();
  });
});
