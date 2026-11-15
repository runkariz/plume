import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ModelSet } from '@/api/types';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { SET_COLLECTION } from '@/mocks/collectionStore';
import { SET_OFFICIAL, SET_UNLISTED, SET_UNRELEASED } from '@/mocks/setStore';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { readCollectionId, saveCollectionId } from '@/lib/collection';
import { editsFor, isChange } from './SetDetail';
import { dimmingSet, layoutSet, parseSetView, relationLabel, withSetView } from './setGraph';

const search = (router: { state: { location: { search: string } } }) =>
  new URLSearchParams(router.state.location.search);
const detail = () => screen.getByRole('region', { name: 'Selected model or relation' });

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE)); // a fresh mock backend per test
});

async function official(): Promise<ModelSet> {
  const r = await fetch(`${TEST_API_BASE}/v1/model-sets/${SET_OFFICIAL}`);
  return (await r.json()) as ModelSet;
}

describe('the diagram: layout and dimming', () => {
  it('puts the models in columns by how far they are from a root, and draws every relation as an arrow', async () => {
    const set = await official();
    const { nodes, edges, dropped } = layoutSet(set);
    expect(dropped).toEqual([]);
    const x = (c: string) => nodes.find((n) => n.id === `m:${c}`)?.position.x ?? -1;
    expect(x('Order')).toBe(0); // nothing points at Order
    expect(x('Product')).toBeGreaterThan(x('Order'));
    expect(x('Variant')).toBeGreaterThan(x('Product'));
    expect(edges.map((e) => [e.id, e.source, e.target])).toEqual([
      ['r:order-items', 'm:Order', 'm:Product'],
      ['r:product-variants', 'm:Product', 'm:Variant'],
    ]);
    expect(edges[0]?.label).toBe('1:n · nested');
    expect(edges[0]?.style?.strokeDasharray).toBeUndefined(); // decided: solid
  });

  it('a proposal is dashed and says so; a relation with an end that is no member is returned, not drawn', async () => {
    const set = await official();
    const proposal = { ...set.relations[0], confirmed: false } as ModelSet['relations'][number];
    expect(relationLabel(proposal)).toBe('proposal · 1:n · nested');
    const odd: ModelSet = {
      ...set,
      relations: [
        proposal,
        { ...(set.relations[1] as ModelSet['relations'][number]), to: 'Ghost' },
      ],
    };
    const { edges, dropped } = layoutSet(odd);
    expect(edges[0]?.style?.strokeDasharray).toBe('7 5');
    expect(dropped).toEqual(['product-variants']);
  });

  it('matches the ends of a relation case-insensitively, as the server does', async () => {
    const set = await official();
    const lower: ModelSet = {
      ...set,
      relations: [
        { ...(set.relations[0] as ModelSet['relations'][number]), from: 'order', to: 'PRODUCT' },
      ],
    };
    const { edges, dropped } = layoutSet(lower);
    expect(dropped).toEqual([]);
    expect(edges[0]).toMatchObject({ source: 'm:Order', target: 'm:Product' });
  });

  it('greys out (never removes) what an unchecked API does not document, and what the filter leaves out', async () => {
    const set = await official();
    // Shopify nests the variants, WooCommerce documents them as a sub-resource: both document both relations here,
    // so give one relation only to Shopify to see the effect
    const onlyShopify: ModelSet = {
      ...set,
      relations: set.relations.map((r) =>
        r.id === 'product-variants'
          ? { ...r, support: { shopify: 'nested', woocommerce: null } }
          : r,
      ),
    };
    const woo = dimmingSet(onlyShopify, { checked: new Set(['woocommerce']), text: '' });
    expect([...woo.edges]).toEqual(['r:product-variants']);
    expect(dimmingSet(onlyShopify, { checked: null, text: '' }).edges.size).toBe(0);
    const filtered = dimmingSet(set, { checked: null, text: 'variant' });
    expect([...filtered.edges]).toEqual(['r:order-items']); // only product-variants matches
    expect(filtered.nodes.has('m:Order')).toBe(true);
    expect(filtered.nodes.has('m:Variant')).toBe(false);
  });

  it('keeps the filter, the checked APIs and the selection in the URL, and ignores what does not exist', async () => {
    const set = await official();
    expect(
      parseSetView(new URLSearchParams('f=ord&show=woocommerce&sel=r:order-items'), set),
    ).toEqual({
      f: 'ord',
      show: ['woocommerce'],
      sel: 'r:order-items',
    });
    expect(parseSetView(new URLSearchParams('sel=r:nope&show=zzz'), set)).toEqual({
      f: '',
      show: null,
      sel: null,
    });
    expect(parseSetView(new URLSearchParams('show=shopify,woocommerce'), set).show).toBeNull(); // all = default
    const p = withSetView(new URLSearchParams('keep=1&f=old'), {
      f: 'new',
      show: ['shopify'],
      sel: 'm:Order',
    });
    expect([p.get('keep'), p.get('f'), p.get('show'), p.get('sel')]).toEqual([
      '1',
      'new',
      'shopify',
      'm:Order',
    ]);
  });
});

describe('the editor: what is staged and what is sent', () => {
  it('a choice is a change unless it is the decided design the relation already has', async () => {
    const set = await official();
    const rel = set.relations[0] as ModelSet['relations'][number];
    const [current, one, ref] = rel.editableOptions ?? [];
    expect(isChange(rel, current as never)).toBe(false);
    expect(isChange({ ...rel, confirmed: false }, current as never)).toBe(true); // confirming a proposal
    expect(isChange(rel, ref as never)).toBe(true);
    expect(one?.editable).toBe(false);
  });

  it("sends the chosen option's own kind, direction, cardinality and fields plus confirmed, only for editable options", async () => {
    const set = await official();
    const variants = set.relations.find(
      (r) => r.id === 'product-variants',
    ) as ModelSet['relations'][number];
    const index = (variants.editableOptions ?? []).findIndex((o) => o.kind === 'reference');
    expect(editsFor(set, { 'product-variants': index })).toEqual([
      {
        id: 'product-variants',
        kind: 'reference',
        cardinality: 'n:1',
        from: 'Variant', // switching to a reference swaps the direction
        to: 'Product',
        ref: { field: 'product_id', key: 'id' },
        confirmed: true,
      },
    ]);
    const items = set.relations.find(
      (r) => r.id === 'order-items',
    ) as ModelSet['relations'][number];
    const notEditable = (items.editableOptions ?? []).findIndex((o) => !o.editable);
    expect(editsFor(set, { 'order-items': notEditable })).toEqual([]);
    expect(editsFor(set, { nope: 0 })).toEqual([]);
  });
});

describe('the model set page', () => {
  it('shows the diagram, the control box (models then relations) and the chips', async () => {
    renderApp(`/model-sets/${SET_OFFICIAL}`);
    expect(await screen.findByRole('heading', { level: 1, name: 'Shop' })).toBeInTheDocument();
    expect(screen.getByText('Official')).toBeInTheDocument();
    expect(screen.getByText('3 models')).toBeInTheDocument();
    expect(screen.getByText('2 relations')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Model set diagram/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(document.querySelectorAll('.react-flow__node-member')).toHaveLength(3),
    );
    const list = screen.getByRole('listbox', { name: 'Models and relations' });
    expect(
      within(list)
        .getAllByRole('option')
        .map((o) => o.querySelector('.wb-row-name')?.textContent),
    ).toEqual(['Order', 'Product', 'Variant', 'Order → Product', 'Product → Variant']);
    expect(
      screen.getByText('Pick a model or a relation in the diagram or in the list.'),
    ).toBeInTheDocument();
  });

  it('a model in the list opens beside the diagram, with its coverage and the way into its field mapping', async () => {
    const { router } = renderApp(`/model-sets/${SET_OFFICIAL}`);
    const list = await screen.findByRole('listbox', { name: 'Models and relations' });
    await userEvent.click(within(list).getByRole('option', { name: /^Variant/ }));
    expect(within(detail()).getByRole('heading', { name: 'Variant' })).toBeInTheDocument();
    expect(within(detail()).getByRole('link', { name: 'Open the field mapping' })).toHaveAttribute(
      'href',
      '/models/m-variant',
    );
    expect(
      within(detail()).getByText(/Called “variant” in Shopify, “variation” in WooCommerce/),
    ).toBeInTheDocument();
    await waitFor(() => expect(search(router).get('sel')).toBe('m:Variant'));
  });

  it('a relation shows how each API documents it, with the quotes, and the designs it could have', async () => {
    renderApp(`/model-sets/${SET_OFFICIAL}?sel=r:order-items`);
    expect(
      await within(
        await screen.findByRole('region', { name: 'Selected model or relation' }),
      ).findByRole('heading', { name: 'Order → Product' }),
    ).toBeInTheDocument();
    const d = detail();
    expect(within(d).getByText('Decided')).toBeInTheDocument();
    const sources = within(d).getByRole('list', { name: 'Sources' });
    expect(within(sources).getAllByText('as nested objects')).toHaveLength(2);
    expect(
      within(sources).getByText(/An array of line items, each with a product_id/),
    ).toBeInTheDocument();
    const radios = within(d).getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect(radios[0]).toBeChecked(); // the current design
    expect(radios[1]).toBeDisabled();
    expect(radios[2]).toBeDisabled();
    // why: what is missing, in the server's words
    expect(
      within(d).getByText(
        /Not possible yet: Product: a field holding the Order id\. Revise the set with Claude/,
      ),
    ).toBeInTheDocument();
  });

  it('an unknown or unreleased set (without the token) is "not found"', async () => {
    const { unmount } = renderApp('/model-sets/nope');
    expect(await screen.findByRole('heading', { name: 'Model set not found' })).toBeInTheDocument();
    unmount();
    renderApp(`/model-sets/${SET_UNRELEASED}`);
    expect(await screen.findByRole('heading', { name: 'Model set not found' })).toBeInTheDocument();
  });
});

describe('editing relations makes a new version', () => {
  it("editing someone else's unlisted set starts this browser's own link: never the author's", async () => {
    // a save without a link always gets a NEW one (the server never answers a link the caller did not send)
    renderApp(`/model-sets/${SET_UNLISTED}?sel=r:product-variants`);
    await screen.findByRole('radio', { name: /Variant refers to Product/ });
    await userEvent.click(screen.getByRole('radio', { name: /Variant refers to Product/ }));
    const bar = screen.getByRole('region', { name: 'Changes to save' });
    await userEvent.click(within(bar).getByRole('button', { name: 'Save as a new version' }));
    expect(await screen.findByText('Saved as a new version')).toBeInTheDocument();
    expect(readCollectionId()).toMatch(/^c-MockCollection\d+$/);
    expect(readCollectionId()).not.toBe(SET_COLLECTION);
    expect(screen.getByText('Your model set is saved, and unlisted')).toBeInTheDocument();
  });

  it('an anonymous visitor editing the official set gets their own unlisted copy and a My models link (kept in this browser)', async () => {
    const { router } = renderApp(`/model-sets/${SET_OFFICIAL}?sel=r:product-variants`);
    await screen.findByRole('radio', { name: /Variant refers to Product/ });
    await userEvent.click(screen.getByRole('radio', { name: /Variant refers to Product/ }));
    expect(within(detail()).getByText(/Staged:/)).toBeInTheDocument();
    const bar = screen.getByRole('region', { name: 'Changes to save' });
    expect(bar).toHaveTextContent('1 relation changed');
    expect(bar).toHaveTextContent('your own unlisted copy');
    await userEvent.click(within(bar).getByRole('button', { name: 'Save as a new version' }));
    expect(await screen.findByText('Saved as a new version')).toBeInTheDocument();
    expect(screen.getByText('Unlisted: anyone with the link')).toBeInTheDocument();
    expect(screen.getByText('Your model set is saved, and unlisted')).toBeInTheDocument();
    expect(readCollectionId()).toMatch(/^c-MockCollection\d+$/);
    expect(screen.getByLabelText('Link to My models')).toHaveValue(
      `${window.location.origin}/mine/${readCollectionId()}`,
    );
    expect(router.state.location.pathname).toMatch(/^\/model-sets\/u-set/);
    // the new version holds the design that was chosen
    await userEvent.click(
      within(screen.getByRole('listbox', { name: 'Models and relations' })).getByRole('option', {
        name: /Product → Variant|Variant → Product/,
      }),
    );
    expect(await screen.findByRole('radio', { name: /Variant refers to Product/ })).toBeChecked();
  });

  it('Undo drops a staged choice; choosing the current decided design stages nothing', async () => {
    renderApp(`/model-sets/${SET_OFFICIAL}?sel=r:product-variants`);
    await userEvent.click(await screen.findByRole('radio', { name: /Variant refers to Product/ }));
    expect(screen.getByRole('region', { name: 'Changes to save' })).toBeInTheDocument();
    await userEvent.click(within(detail()).getByRole('radio', { name: /Product embeds Variant/ }));
    expect(screen.queryByRole('region', { name: 'Changes to save' })).not.toBeInTheDocument();
    await userEvent.click(
      within(detail()).getByRole('radio', { name: /Variant refers to Product/ }),
    );
    await userEvent.click(within(detail()).getByRole('button', { name: 'Undo' }));
    expect(screen.queryByRole('region', { name: 'Changes to save' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Filter models and relations/ }));
  });

  it('shows the refusal of the server (422) with its codes, and a 409 with the way to the latest version', async () => {
    renderApp(`/model-sets/${SET_OFFICIAL}?sel=r:product-variants`);
    await userEvent.click(await screen.findByRole('radio', { name: /Variant refers to Product/ }));
    server.use(
      http.post(
        `${TEST_API_BASE}/v1/model-sets/:id/relations`,
        () =>
          HttpResponse.json(
            {
              error: 'design_refused',
              message: 'refused',
              issues: [
                {
                  code: 'RELATION_SHAPE_MISMATCH',
                  field: 'product-variants',
                  api: null,
                  message: 'needs a field',
                },
              ],
            },
            { status: 422 },
          ),
        { once: true },
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save as a new version' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('That design was refused, nothing was saved.');
    expect(within(alert).getByText('RELATION_SHAPE_MISMATCH')).toBeInTheDocument();
    server.use(
      http.post(
        `${TEST_API_BASE}/v1/model-sets/:id/relations`,
        () => HttpResponse.json({ error: 'not_latest', message: 'x' }, { status: 409 }),
        { once: true },
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save as a new version' }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('not the latest version'),
    );
  });

  it('a version that is not the latest cannot be edited: the page says so and links to the latest', async () => {
    // v1 -> v2 by saving, then open v1 again
    const { unmount } = renderApp(`/model-sets/${SET_UNLISTED}?sel=r:product-variants`);
    await userEvent.click(await screen.findByRole('radio', { name: /Variant refers to Product/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Save as a new version' }));
    await screen.findByText('Saved as a new version');
    unmount();
    renderApp(`/model-sets/${SET_UNLISTED}?sel=r:product-variants`);
    expect(await screen.findByText('A newer version of this model set exists')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the latest version' })).toBeInTheDocument();
    for (const r of await screen.findAllByRole('radio')) expect(r).toBeDisabled();
  });
});

describe('release (maintainer)', () => {
  it('is blocked while a relation is undecided, says which, and goes on after the relation is decided', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(`/model-sets/${SET_UNRELEASED}`);
    expect(await screen.findByText('Unreleased: waiting for your review')).toBeInTheDocument();
    expect(screen.getByText('1 to decide')).toBeInTheDocument();
    const release = screen.getByRole('button', { name: 'Release' });
    expect(release).toBeDisabled();
    expect(
      screen
        .getAllByRole('status')
        .some((e) =>
          /Release is blocked: 1 relation is not decided yet: Order → Product/.test(
            e.textContent ?? '',
          ),
        ),
    ).toBe(true);
    // the link in the message selects the relation; its proposal is shown as such
    await userEvent.click(screen.getByRole('button', { name: 'Order → Product' }));
    expect(within(detail()).getByText('Proposal: to decide')).toBeInTheDocument();
    expect(
      within(detail()).getByText('Pick a design to confirm this relation.'),
    ).toBeInTheDocument();
    // decide it: a new unreleased version with nothing to decide
    await userEvent.click(within(detail()).getAllByRole('radio')[0] as HTMLElement);
    expect(screen.getByRole('region', { name: 'Changes to save' })).toHaveTextContent(
      'a new unreleased version',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save as a new version' }));
    await screen.findByText('Saved as a new version');
    expect(screen.queryByText(/to decide/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Release' }));
    expect(await screen.findByText('Released: the set is Official')).toBeInTheDocument();
    // it stays (the page must not start again), and the set now says Official
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.getByText('Released: the set is Official')).toBeInTheDocument();
    expect(screen.getAllByText('Official', { selector: '.chip' }).length).toBeGreaterThan(0);
    expect(screen.queryByText('Unreleased: waiting for your review')).not.toBeInTheDocument();
    // the models released with it, by name
    const released = screen
      .getByText('These models were released with it:')
      .closest('div') as HTMLElement;
    expect(within(released).getByRole('link', { name: 'Order' })).toHaveAttribute(
      'href',
      '/models/m-order',
    );
    expect(within(released).queryByRole('link', { name: 'Variant' })).not.toBeInTheDocument(); // it was not available
  });

  it('a 409 from the server is explained, and Discard asks to confirm', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(`/model-sets/${SET_UNRELEASED}`);
    await screen.findByText('Unreleased: waiting for your review');
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByText('Discard this set? It cannot be undone.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(screen.queryByText(/cannot be undone/)).not.toBeInTheDocument();
  });

  it('shows missing members as not available', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp(`/model-sets/${SET_UNRELEASED}?sel=m:Variant`);
    expect(
      await within(
        await screen.findByRole('region', { name: 'Selected model or relation' }),
      ).findByText('Not available'),
    ).toBeInTheDocument();
    expect(screen.getByText(/not released, or you cannot see it/)).toBeInTheDocument();
  });
});

describe('the lists', () => {
  it('the Models page lists the official sets; the unreleased only for a maintainer; "Your model sets" from the My models link', async () => {
    const { unmount } = renderApp('/models');
    const official = await screen.findByRole('region', { name: 'Official model sets' });
    expect(within(official).getByRole('link', { name: 'Shop' })).toHaveAttribute(
      'href',
      `/model-sets/${SET_OFFICIAL}`,
    );
    expect(within(official).getByText('Official')).toBeInTheDocument();
    expect(within(official).queryByText('Catalog (draft)')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('region', { name: 'Sets waiting for review' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Your model sets' })).not.toBeInTheDocument();
    unmount();
    authStore.signIn('pl_ok', 'maintainer');
    saveCollectionId(SET_COLLECTION);
    renderApp('/models');
    const waiting = await screen.findByRole('region', { name: 'Sets waiting for review' });
    expect(within(waiting).getByRole('link', { name: 'Catalog (draft)' })).toBeInTheDocument();
    expect(within(waiting).getByText('1 to decide')).toBeInTheDocument();
    const mine = await screen.findByRole('region', { name: 'Your model sets' });
    expect(within(mine).getByRole('link', { name: 'Shop (my version)' })).toBeInTheDocument();
  });
});
