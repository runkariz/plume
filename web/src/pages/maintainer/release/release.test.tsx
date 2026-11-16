import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { REVIEW_SHOPIFY_FIRST, REVIEW_SHOPIFY_NEW, REVIEW_SHOPIFY_OLD } from '@/mocks/releaseStore';
import { ApiProvider } from '@/api/context';
import { renderApp, testClient } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import type { ChangeItem } from '@/api/types';
import { ChangeRow } from './ChangeRow';
import { safeHref, subjectText, valueText } from './notes';

const notes = `/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`;

beforeEach(() => {
  localStorage.clear();
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_ok', 'maintainer');
});
afterEach(() => authStore.signOut());

const open = async (path = notes) => {
  const view = renderApp(path);
  await screen.findByRole('heading', { level: 1, name: 'Release review: shopify' });
  return view;
};

describe('wording and safety of what a package says', () => {
  it('links only http(s) addresses', () => {
    expect(safeHref('https://shopify.dev/x')).toBe('https://shopify.dev/x');
    expect(safeHref('http://example.com/a')).toBe('http://example.com/a');
    for (const bad of [
      'javascript:alert(1)',
      'data:text/html,<b>x',
      'ftp://x/y',
      '/relative',
      'not a url',
      '',
      null,
      undefined,
    ])
      expect(safeHref(bad as string | null | undefined), String(bad)).toBeNull();
  });
  it('names the subject and the values', () => {
    const i = {
      id: 'x',
      kind: 'param',
      op: 'removed',
      class: 'confirmed',
      breaking: true,
      subject: { method: 'GET', path: '/orders.json' },
    } as ChangeItem;
    expect(subjectText(i)).toBe('GET /orders.json');
    expect(subjectText({ ...i, subject: { model: 'Order' } })).toBe('Order model');
    expect(subjectText({ ...i, subject: { docId: 'auth:oauth' } })).toBe('auth:oauth');
    expect(valueText({ type: 'string', required: false })).toBe('string, optional');
    expect(valueText({ required: true })).toBe('required');
    expect(valueText({ quote: 'x' })).toBe('described');
    expect(valueText(null)).toBe('none');
  });
});

describe('the builds of an API', () => {
  it('lists them newest first, with the review state, and links only builds that have notes', async () => {
    renderApp('/maintainer/apis/shopify/builds');
    const list = await screen.findByRole('list', { name: 'Builds' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('b-shopify-2026');
    expect(within(rows[0] as HTMLElement).getByText('Pending review')).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText('Needs attention')).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText('latest')).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByRole('link')).toHaveAttribute(
      'href',
      `/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`,
    );
    expect(within(rows[1] as HTMLElement).getByText('Kept')).toBeInTheDocument();
    // the first build has nothing to compare with: no notes, no link
    expect(within(rows[2] as HTMLElement).getByText('no notes')).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).queryByRole('link')).not.toBeInTheDocument();
  });

  it('says so when there are no builds with notes', async () => {
    renderApp('/maintainer/apis/mirakl/builds');
    expect(await screen.findByText('No builds with release notes')).toBeInTheDocument();
  });
});

describe('the entry links (feature detection)', () => {
  it('the maintainer home links the review of an API whose latest build has notes, and flags attention', async () => {
    renderApp('/maintainer');
    const link = await screen.findByRole('link', { name: 'Release review' });
    expect(link).toHaveAttribute(
      'href',
      `/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_NEW}/notes`,
    );
    expect(await screen.findAllByText('Needs attention')).toHaveLength(1);
    // WooCommerce and the others have no notes: no link for them
    expect(screen.getAllByRole('link', { name: 'Release review' })).toHaveLength(1);
  });
});

describe('the review of a build', () => {
  it('shows the status, why it needs attention (nothing is held), what changed, the package and the quality', async () => {
    await open();
    const head = screen.getByRole('heading', { level: 1 }).closest('div') as HTMLElement;
    expect(within(head).getByText('Latest')).toBeInTheDocument();
    expect(within(head).getByText('Pending review')).toBeInTheDocument();
    expect(within(head).getByText('Needs attention')).toBeInTheDocument();
    const banner = screen
      .getByText('Needs attention', { selector: 'h3' })
      .closest('div') as HTMLElement;
    expect(banner).toHaveTextContent('alphabetical cut-off');
    expect(banner).toHaveTextContent('Nothing is held: this build is live');
    const counts = screen.getByRole('region', { name: 'What changed' });
    expect(counts).toHaveTextContent('3 confirmed in the docs');
    expect(counts).toHaveTextContent('1 likely');
    expect(counts).toHaveTextContent('5 suspect');
    expect(counts).toHaveTextContent('1 without source evidence');
    const pkg = screen.getByRole('region', { name: 'Package and quality' });
    expect(pkg).toHaveTextContent('1.4.2 → 1.4.3');
    expect(pkg).toHaveTextContent('rules-7f3a → rules-9b21');
    expect(pkg).toHaveTextContent('0.94 → 0.91');
  });

  it("groups the suspect changes by rule with the server's own explanation, and keeps them out of what users see", async () => {
    await open();
    const cut = screen.getByRole('region', { name: 'Alphabetical cut-off' });
    expect(cut).toHaveTextContent('the extraction stopped early, the docs did not change');
    expect(within(cut).getAllByRole('listitem')).toHaveLength(3);
    expect(within(cut).getAllByText('Suspect: extraction artifact').length).toBe(3);
    expect(within(cut).getAllByText(/the source page did not change/).length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: 'Property count drop' })).toBeInTheDocument();
    const unknown = screen.getByRole('region', { name: 'No source evidence' });
    expect(
      within(unknown).getByText('No source evidence', { selector: '.chip' }),
    ).toBeInTheDocument();
    // users see the confirmed and likely ones only
    const visible = screen.getByRole('region', { name: 'Changes users see' });
    expect(within(visible).getAllByRole('listitem')).toHaveLength(4);
    expect(within(visible).queryByText(/Suspect/)).not.toBeInTheDocument();
    expect(within(visible).getByText('Likely (vendor changelog)')).toBeInTheDocument();
    expect(within(visible).getAllByText('Breaking').length).toBe(2);
  });

  it('renders the package text as text, and links only the vendor page', async () => {
    const evil: ChangeItem = {
      id: 'ch-evil',
      kind: 'response_field',
      op: 'removed',
      class: 'confirmed',
      breaking: true,
      breakingReason: '<b>bold</b>',
      subject: {
        method: 'GET',
        path: '/<script>alert(1)</script>',
        fieldPath: '<img src=x onerror=alert(1)>',
      },
      before: { quote: '<img src=x onerror="alert(1)">' },
      after: null,
      evidence: { sourceUrl: 'javascript:alert(1)' },
    };
    render(
      <ApiProvider client={testClient()}>
        <ul>
          <ChangeRow api="shopify" build="b" item={evil} onChanged={() => undefined} />
        </ul>
      </ApiProvider>,
    );
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText('<b>bold</b>')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument(); // javascript: is not a link
    expect(screen.getByText('No vendor page')).toBeInTheDocument();
  });

  it('Keep records the decision and the status becomes Kept', async () => {
    await open();
    await userEvent.type(
      screen.getByLabelText('Note for the record (optional)'),
      'Checked Order by hand',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Keep this build' }));
    await waitFor(() => expect(screen.getAllByText('Kept').length).toBeGreaterThan(0));
    expect(screen.queryByRole('button', { name: 'Keep this build' })).not.toBeInTheDocument();
    const history = screen.getByRole('region', { name: 'History' });
    expect(within(history).getByText('Checked Order by hand')).toBeInTheDocument();
    expect(within(history).getByText('Kept')).toBeInTheDocument();
  });

  it('Roll back needs a reason, says what happens, moves the tag back, and can be rolled forward', async () => {
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Roll back…' }));
    const dialog = screen.getByRole('group', { name: 'Roll back this build' });
    expect(dialog).toHaveTextContent('The tag latest moves back to');
    expect(dialog).toHaveTextContent('you can roll it forward again');
    const go = within(dialog).getByRole('button', { name: 'Roll back' });
    expect(go).toBeDisabled(); // a reason is required
    await userEvent.type(within(dialog).getByLabelText(/Reason/), 'Order lost its fields m to z');
    expect(within(dialog).getByText('28 of 500')).toBeInTheDocument();
    await userEvent.click(go);
    expect(await screen.findByText(/Rolled back: `latest` is b-shopify-2026/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('Rolled back').length).toBeGreaterThan(0));
    expect(screen.getByText('Not latest')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Roll back…' })).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'History' })).getByText(
        'Order lost its fields m to z',
      ),
    ).toBeInTheDocument();
    // undo: roll forward
    await userEvent.click(screen.getByRole('button', { name: 'Roll forward' }));
    expect(await screen.findByText('Latest')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'History' })).getByText('Rolled forward'),
    ).toBeInTheDocument();
  });

  it('a refused rollback (409) says why and changes nothing', async () => {
    server.use(
      http.post(`${TEST_API_BASE}/v1/apis/:id/builds/:build/release-notes/rollback`, () =>
        HttpResponse.json({ error: 'invalid_state', message: 'latest moved on' }, { status: 409 }),
      ),
    );
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Roll back…' }));
    await userEvent.type(screen.getByLabelText(/Reason/), 'because');
    await userEvent.click(screen.getByRole('button', { name: 'Roll back' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Rolling back is not possible now: latest moved on',
    );
    expect(screen.getByText('Pending review')).toBeInTheDocument();
  });

  it('an older build that is not latest cannot be rolled back, and the first build has no notes', async () => {
    await open(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_OLD}/notes`);
    expect(screen.queryByRole('button', { name: 'Roll back…' })).not.toBeInTheDocument();
    expect(screen.getByText(/is not `latest`, so it cannot be rolled back/)).toBeInTheDocument();
  });

  it('a build without notes says so (the first build has nothing to compare with)', async () => {
    renderApp(`/maintainer/apis/shopify/builds/${REVIEW_SHOPIFY_FIRST}/notes`);
    expect(await screen.findByText('No release notes for this build')).toBeInTheDocument();
  });

  it("Copy issues puts the server's text on the clipboard; a refused clipboard says to use the download", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Copy issues' }));
    expect(await screen.findByText('Issues copied: paste them to stream')).toBeInTheDocument();
    const text = String(writeText.mock.calls[0]?.[0]);
    expect(text).toContain('# Extraction issues: shopify, build b-shopify-20261114');
    expect(text).toContain('stream 1.4.2 -> 1.4.3');
    expect(text).toContain('## A2-alphabetical-cutoff');
    writeText.mockRejectedValue(new Error('denied'));
    await userEvent.click(screen.getByRole('button', { name: 'Copy issues' }));
    expect(await screen.findByText('Copy failed: use the download instead')).toBeInTheDocument();
  });

  it('Download issues saves the same text as a .md file', async () => {
    const created: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => {
      created.push(b as Blob);
      return 'blob:x';
    });
    URL.revokeObjectURL = vi.fn();
    const clicks: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicks.push(this.download);
    });
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Download issues (.md)' }));
    await waitFor(() => expect(clicks).toEqual([`shopify-${REVIEW_SHOPIFY_NEW}-issues.md`]));
    expect(created[0]?.type).toBe('text/markdown');
    expect(await created[0]?.text()).toContain('# Extraction issues');
    click.mockRestore();
  });

  it('Promote asks for a quote the server verifies: a wrong one is refused, a right one makes it confirmed, and it can be demoted', async () => {
    await open();
    const cut = screen.getByRole('region', { name: 'Alphabetical cut-off' });
    const row = within(cut).getAllByRole('listitem')[0] as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: 'Promote to confirmed…' }));
    const box = within(row).getByLabelText(/A quote from the vendor docs/);
    await userEvent.type(box, 'This sentence is not in the page at all.');
    await userEvent.click(within(row).getByRole('button', { name: 'Promote to confirmed' }));
    expect(await within(row).findByRole('alert')).toHaveTextContent(
      'not in the source text of this build',
    );
    expect(within(row).getByText('Suspect: extraction artifact')).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, 'shipping_lines: the shipping lines of the order.');
    await userEvent.click(within(row).getByRole('button', { name: 'Promote to confirmed' }));
    // it left the report and now shows with the others users see, as promoted by hand
    const visible = await screen.findByRole('region', { name: 'Changes users see' });
    await waitFor(() => expect(within(visible).getByText('Promoted by hand')).toBeInTheDocument());
    expect(
      within(screen.getByRole('region', { name: 'Alphabetical cut-off' })).getAllByRole('listitem'),
    ).toHaveLength(2);
    expect(
      within(screen.getByRole('region', { name: 'History' })).getByText('Promoted to confirmed'),
    ).toBeInTheDocument();
    await userEvent.click(within(visible).getByRole('button', { name: 'Demote' }));
    await waitFor(() =>
      expect(
        within(screen.getByRole('region', { name: 'Alphabetical cut-off' })).getAllByRole(
          'listitem',
        ),
      ).toHaveLength(3),
    );
  });

  it('is not shown to someone without a maintainer session', async () => {
    authStore.signOut();
    renderApp(notes);
    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: 'Release review: shopify' }),
      ).not.toBeInTheDocument(),
    );
  });
});
