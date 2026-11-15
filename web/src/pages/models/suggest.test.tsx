import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { sampleSuggestions } from '@/mocks/modelData';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { changed, isFiltered, PAGE_SIZE, parseView, toQuery, withView } from './suggestQuery';

const APIS = ['shopify', 'woocommerce', 'mirakl'];
const url = `/models/suggest?apis=${APIS.join(',')}`;

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
});

const names = () => screen.getAllByRole('article').map((a) => a.getAttribute('aria-label'));
const search = (router: { state: { location: { search: string } } }) =>
  new URLSearchParams(router.state.location.search);

describe('suggestions: search', () => {
  it('searches the concepts after a short pause and keeps the search in the URL', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('heading', { name: 'Product' });
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search concepts' }), 'refund');
    await waitFor(() => expect(names()).toEqual(['Refund']));
    expect(search(router).get('q')).toBe('refund');
    expect(screen.queryByRole('heading', { name: 'Product' })).not.toBeInTheDocument();
  });

  it('says so when nothing matches, and Clear filters brings everything back', async () => {
    renderApp(`${url}&q=zzzznothing`);
    expect(await screen.findByText('No concepts match these filters')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear the filters' }));
    expect(await screen.findByRole('heading', { name: 'Product' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Search concepts' })).toHaveValue('');
  });
});

describe('suggestions: per-API filter', () => {
  const fieldset = () => screen.getByRole('group', { name: 'Only concepts that exist in' });

  it('checking Shopify + WooCommerce shows only concepts present in BOTH, in the URL', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('heading', { name: 'Invoice' }); // Mirakl and WooCommerce, not Shopify
    await userEvent.click(within(fieldset()).getByRole('checkbox', { name: 'Shopify' }));
    await userEvent.click(within(fieldset()).getByRole('checkbox', { name: 'WooCommerce' }));
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Invoice' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('heading', { name: 'Discount' })).toBeInTheDocument(); // direct in both
    expect(screen.getByRole('heading', { name: 'Shipment' })).toBeInTheDocument(); // direct + derived
    expect(screen.queryByRole('heading', { name: 'Return' })).not.toBeInTheDocument(); // absent in WooCommerce
    expect(search(router).get('require')).toBe('shopify,woocommerce');
    // every concept shown has no "absent" in the two checked APIs
    for (const a of screen.getAllByRole('article')) {
      expect(within(a).queryByLabelText('Shopify (absent)')).not.toBeInTheDocument();
      expect(within(a).queryByLabelText('WooCommerce (absent)')).not.toBeInTheDocument();
    }
  });

  it('two quick clicks both count (each change starts from the latest filters)', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('heading', { name: 'Product' });
    // no await in between: the second click happens before the router applied the first
    fireEvent.click(within(fieldset()).getByRole('checkbox', { name: 'Shopify' }));
    fireEvent.click(within(fieldset()).getByRole('checkbox', { name: 'Mirakl' }));
    await waitFor(() => expect(search(router).get('require')).toBe('shopify,mirakl'));
    expect(within(fieldset()).getByRole('checkbox', { name: 'Shopify' })).toBeChecked();
    expect(within(fieldset()).getByRole('checkbox', { name: 'Mirakl' })).toBeChecked();
  });

  it('combines with the chips: Can write narrows the same list', async () => {
    renderApp(`${url}&require=shopify,woocommerce`);
    await screen.findByRole('heading', { name: 'Tax' }); // read only
    await userEvent.click(screen.getByRole('radio', { name: /^Can write/ }));
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Tax' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('heading', { name: 'Discount' })).toBeInTheDocument();
    expect(within(fieldset()).getByRole('checkbox', { name: 'Shopify' })).toBeChecked();
  });

  it('shows the chip numbers the server counted for the current filters', async () => {
    renderApp(`${url}&require=shopify,woocommerce`);
    const expected = sampleSuggestions(APIS, { require: ['shopify', 'woocommerce'] }).counts;
    expect(
      await screen.findByRole('radio', { name: `All concepts · ${expected.all}` }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('radio', { name: `Can write · ${expected.write}` }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('radio', { name: `In all 3 APIs · ${expected.inAll}` }),
    ).toBeInTheDocument();
  });

  it('ignores an id in the URL that is not one of the selected APIs', async () => {
    renderApp(`${url}&require=github`);
    await screen.findByRole('heading', { name: 'Product' });
    expect(
      within(fieldset())
        .getAllByRole('checkbox')
        .filter((c) => (c as HTMLInputElement).checked),
    ).toHaveLength(0);
  });
});

describe('suggestions: concepts that exist in only one API', () => {
  it('a switch lists them; the shared-concept chips go away', async () => {
    const { router } = renderApp(url);
    await screen.findByRole('heading', { name: 'Product' });
    await userEvent.click(screen.getByRole('radio', { name: /^Only in one API/ }));
    expect(await screen.findByRole('heading', { name: 'Theme' })).toBeInTheDocument(); // Shopify only
    expect(screen.getByRole('heading', { name: 'Supplier' })).toBeInTheDocument(); // Mirakl only
    expect(screen.queryByRole('heading', { name: 'Product' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /^Can write/ })).not.toBeInTheDocument();
    expect(search(router).get('only')).toBe('single');
  });

  it('the "not modeled" card links to them and back', async () => {
    renderApp(url);
    await userEvent.click(
      await screen.findByRole('button', { name: 'Browse the concepts that exist in only one API' }),
    );
    expect(await screen.findByRole('heading', { name: 'Theme' })).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Back to concepts shared by several APIs' }),
    );
    expect(await screen.findByRole('heading', { name: 'Product' })).toBeInTheDocument();
  });
});

describe('suggestions: the "not modeled" card follows the filters', () => {
  it('says what the filters leave instead of "every resource is covered"', async () => {
    renderApp(`${url}&q=product`);
    await screen.findByRole('heading', { name: 'Product' });
    expect(screen.queryByText(/Every resource found in these APIs/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/No concept that exists in only one API matches these filters\./),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Browse the concepts that exist in only one API' }),
    ).not.toBeInTheDocument();
  });

  it('with filters that leave single-API concepts it counts them and links to them', async () => {
    renderApp(`${url}&q=theme`);
    expect(await screen.findByText('No concepts match these filters')).toBeInTheDocument();
    expect(
      screen.getByText(/1 concept that exist in only one of these APIs match/),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Browse the concepts that exist in only one API' }),
    );
    expect(await screen.findByRole('heading', { name: 'Theme' })).toBeInTheDocument();
  });
});

describe('suggestions: paging', () => {
  const total = sampleSuggestions(APIS).total;

  it('shows a page at a time with Previous / Next, the page in the URL', async () => {
    expect(total).toBeGreaterThan(PAGE_SIZE);
    const { router } = renderApp(url);
    await screen.findByRole('heading', { name: 'Product' });
    expect(screen.getAllByRole('article')).toHaveLength(PAGE_SIZE);
    expect(
      screen.getByText(new RegExp(`Showing 1–${PAGE_SIZE} of ${total} concepts`)),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(total - PAGE_SIZE));
    expect(search(router).get('page')).toBe('2');
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(PAGE_SIZE));
    expect(search(router).get('page')).toBeNull();
  });

  it('opens on the page in the URL, and a filter goes back to page 1', async () => {
    const { router } = renderApp(`${url}&page=2`);
    await screen.findByRole('heading', { name: 'Fulfillment' });
    expect(screen.queryByRole('heading', { name: 'Product' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: /^Can write/ }));
    await waitFor(() => expect(search(router).get('page')).toBeNull());
    expect(search(router).get('write')).toBe('1');
  });

  it('a page beyond the end offers the first page', async () => {
    renderApp(`${url}&page=9`);
    expect(await screen.findByText('That page is empty')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Back to the first page' }));
    expect(await screen.findByRole('heading', { name: 'Product' })).toBeInTheDocument();
  });

  it('Regenerate finds a concept that is not on the first page', async () => {
    renderApp(`${url}&regenerate=Fulfillment`);
    expect(
      await screen.findByRole('heading', { name: 'Waiting for a draft: Fulfillment' }),
    ).toBeInTheDocument();
  });
});

describe('suggestions: the reason and the icons', () => {
  it('shows the reason under the box and no "documented by" line', async () => {
    renderApp(url);
    const card = (await screen.findByRole('heading', { name: 'Order' })).closest(
      'article',
    ) as HTMLElement;
    expect(
      within(card).getByText(/^Order is documented as a model in Shopify, WooCommerce and Mirakl/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/as documented by/)).not.toBeInTheDocument();
    const counts = within(card).getByRole('list', { name: 'Order in each API' });
    expect(within(counts).getAllByRole('listitem')).toHaveLength(3);
    expect(
      within(counts).getAllByText(/models? · \d+ endpoints? · \d+ fields · read, create, update/),
    ).toHaveLength(3);
  });

  it('shows the package icon where an API is shown, the letter where there is none', async () => {
    renderApp(url);
    await screen.findByRole('heading', { name: 'Product' });
    const chips = screen.getByRole('list', { name: 'Selected APIs' });
    const shopify = within(chips).getByText('Shopify').closest('li') as HTMLElement;
    expect(shopify.querySelector('img')).toHaveAttribute(
      'src',
      `${TEST_API_BASE}/v1/apis/shopify/icon`,
    );
    const woo = within(chips).getByText('WooCommerce').closest('li') as HTMLElement;
    expect(woo.querySelector('img')).toBeNull();
    expect(woo).toHaveTextContent('W');
    // the coverage circles of a concept and the filter checkboxes too
    const card = screen.getByRole('heading', { name: 'Product' }).closest('article') as HTMLElement;
    expect(within(card).getByLabelText('Shopify').querySelector('img')).toBeInTheDocument();
    const box = screen.getByRole('checkbox', { name: 'Shopify' }).closest('label') as HTMLElement;
    expect(box.querySelector('img')).toBeInTheDocument();
  });

  it('the app pickers of /models show the icons too', async () => {
    renderApp('/models');
    const shopify = (await screen.findByRole('checkbox', { name: /Shopify/ })).closest(
      'label',
    ) as HTMLElement;
    expect(shopify.querySelector('img')).toHaveAttribute(
      'src',
      `${TEST_API_BASE}/v1/apis/shopify/icon`,
    );
    const woo = screen
      .getByRole('checkbox', { name: /WooCommerce/ })
      .closest('label') as HTMLElement;
    expect(woo.querySelector('img')).toBeNull();
    // and in the selection bar
    await userEvent.click(screen.getByRole('checkbox', { name: /Shopify/ }));
    const bar = screen.getByRole('region', { name: 'Selected APIs' });
    expect(bar.querySelector('img')).toBeInTheDocument();
  });
});

describe('suggestQuery', () => {
  const apis = ['a', 'b'];
  it('reads the view from the URL with safe defaults', () => {
    expect(parseView(new URLSearchParams(''), apis)).toEqual({
      q: '',
      only: 'multi',
      require: [],
      chip: 'all',
      page: 1,
    });
    expect(
      parseView(new URLSearchParams('q= x &only=single&require=a,zzz,b&inAll=1&page=3'), apis),
    ).toEqual({
      q: 'x',
      only: 'single',
      require: ['a', 'b'],
      chip: 'every',
      page: 3,
    });
    expect(parseView(new URLSearchParams('only=nope&page=-4&write=1'), apis)).toMatchObject({
      only: 'multi',
      page: 1,
      chip: 'write',
    });
  });

  it('builds the request: chips apply only to shared concepts, page becomes an offset', () => {
    const v = parseView(new URLSearchParams('inAll=1&page=3&require=a'), apis);
    expect(toQuery(v)).toMatchObject({
      inAll: true,
      require: ['a'],
      limit: PAGE_SIZE,
      offset: 2 * PAGE_SIZE,
    });
    expect(toQuery({ ...v, only: 'single' }).inAll).toBeUndefined();
  });

  it('writes the view back and keeps the other parameters', () => {
    const base = new URLSearchParams('apis=a,b&regenerate=Order&q=old&page=2');
    const p = withView(base, changed(parseView(base, apis), { q: 'new', require: ['b'] }));
    expect(p.get('apis')).toBe('a,b');
    expect(p.get('regenerate')).toBe('Order');
    expect(p.get('q')).toBe('new');
    expect(p.get('require')).toBe('b');
    expect(p.get('page')).toBeNull(); // a filter goes back to page 1
    expect(isFiltered(parseView(new URLSearchParams(''), apis))).toBe(false);
    expect(isFiltered(parseView(p, apis))).toBe(true);
  });
});
