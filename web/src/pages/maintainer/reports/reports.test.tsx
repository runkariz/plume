import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { shortSession, statusLabel, statusTone } from './labels';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_test_token_value');
});
afterEach(() => authStore.signOut());

describe('labels', () => {
  it('names the statuses and leaves an unknown one as written', () => {
    expect(statusLabel('search-miss')).toBe('Search miss');
    expect(statusLabel('later-status')).toBe('later-status');
    expect(statusTone('open')).toBe('warn');
    expect(statusTone('later-status')).toBe('neutral');
  });
  it('shortens a session hash', () => {
    expect(shortSession('9f8e7d6c5b4a3921')).toBe('9f8e7d6c');
    expect(shortSession(null)).toBeNull();
  });
});

describe('the reports list', () => {
  it('lists the reports most reported first, with counts, status and the redacted text as it is', async () => {
    renderApp('/maintainer/reports');
    const list = await screen.findByRole('list', { name: 'Reports' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent('How do I page through all orders');
    expect(within(rows[0] as HTMLElement).getByText('4 reports')).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText('Open')).toBeInTheDocument();
    // markers stay as the server wrote them
    expect(within(list).getByText(/Token \[token\] is rejected/)).toBeInTheDocument();
    // the reason of a triaged report is shown
    expect(within(list).getByText(/GraphQL is a separate API/)).toBeInTheDocument();
    expect(screen.getByText('4 reports', { selector: 'p' })).toBeInTheDocument();
  });

  it('filters by status and by API, in the URL', async () => {
    const { router } = renderApp('/maintainer/reports');
    await screen.findByRole('list', { name: 'Reports' });
    await userEvent.click(screen.getByRole('radio', { name: 'Answered' }));
    await waitFor(() => expect(router.state.location.search).toBe('?status=answered'));
    const list = await screen.findByRole('list', { name: 'Reports' });
    await waitFor(() => expect(within(list).getAllByRole('listitem')).toHaveLength(1));
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.selectOptions(screen.getByLabelText('API'), 'stripe');
    await waitFor(() => expect(router.state.location.search).toBe('?api=stripe'));
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Reports' })).getAllByRole('listitem'),
      ).toHaveLength(1),
    );
  });

  it('says so when nothing matches', async () => {
    renderApp('/maintainer/reports?status=package-gap');
    expect(await screen.findByText('No report matches this filter.')).toBeInTheDocument();
  });

  it('says reporting is off when the server says enabled: false, and still lists the reports', async () => {
    server.use(
      http.get(`${TEST_API_BASE}/v1/maintainer/reports`, () =>
        HttpResponse.json({ reports: [], enabled: false }),
      ),
    );
    renderApp('/maintainer/reports');
    expect(
      await screen.findByText('Reported questions are off on this server'),
    ).toBeInTheDocument();
    expect(screen.getByText('Nothing has been reported yet.')).toBeInTheDocument();
  });

  it('shows no such notice when reporting is on, or an older server sends no flag', async () => {
    renderApp('/maintainer/reports');
    await screen.findByRole('list', { name: 'Reports' });
    expect(screen.queryByText('Reported questions are off on this server')).not.toBeInTheDocument();
  });

  it('a reader without the token is sent to sign in', async () => {
    authStore.signOut();
    renderApp('/maintainer/reports');
    // the sign-in page, not the list
    expect(await screen.findByLabelText('Access token')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Reports' })).not.toBeInTheDocument();
  });

  it('is linked from the maintainer home', async () => {
    renderApp('/maintainer');
    expect(await screen.findByRole('link', { name: 'Reported questions' })).toHaveAttribute(
      'href',
      '/maintainer/reports',
    );
  });
});

describe('one report', () => {
  const url = '/maintainer/reports/rq-1a2b3c4d5e';

  it('shows what was reported and its notes, duplicates marked, redaction counts and sessions', async () => {
    renderApp(url);
    const what = await screen.findByRole('region', { name: 'The report' });
    expect(what).toHaveTextContent('Which filters can be combined with page_info');
    expect(what).toHaveTextContent('session 9f8e7d6c');
    const notes = screen.getByRole('list', { name: 'Notes on this report' });
    const items = within(notes).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(within(items[0] as HTMLElement).getByText('duplicate report')).toBeInTheDocument();
    expect(items[1]).toHaveTextContent('Account [account] hit it.');
    expect(items[1]).toHaveTextContent('1 redacted');
  });

  it('saves a status with a reason, and says readers see it for answered and out-of-scope', async () => {
    renderApp(url);
    const form = await screen.findByRole('form', { name: 'Triage' });
    const save = within(form).getByRole('button', { name: 'Save status' });
    expect(save).toBeDisabled(); // nothing changed
    await userEvent.click(within(form).getByRole('radio', { name: 'Answered' }));
    expect(within(form).getByText(/Readers see this reason/)).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText('Reason'), 'Page_info cannot be combined.');
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(await within(form).findByText('Saved.')).toBeInTheDocument();
    expect(save).toBeDisabled();
    // the page reflects it
    expect(screen.getAllByText('Answered').length).toBeGreaterThan(0);
  });

  it('does not say readers see the reason for the other statuses', async () => {
    renderApp(url);
    const form = await screen.findByRole('form', { name: 'Triage' });
    await userEvent.click(within(form).getByRole('radio', { name: 'Package gap' }));
    expect(within(form).queryByText(/Readers see this reason/)).not.toBeInTheDocument();
  });

  it('shows the server error when the save is refused', async () => {
    server.use(
      http.patch(`${TEST_API_BASE}/v1/maintainer/reports/:id`, () =>
        HttpResponse.json({ detail: 'nope' }, { status: 422 }),
      ),
    );
    renderApp(url);
    const form = await screen.findByRole('form', { name: 'Triage' });
    await userEvent.click(within(form).getByRole('radio', { name: 'Search miss' }));
    await userEvent.click(within(form).getByRole('button', { name: 'Save status' }));
    expect(await within(form).findByRole('alert')).toBeInTheDocument();
  });

  it('an unknown report is "not found"', async () => {
    renderApp('/maintainer/reports/rq-nope');
    expect(await screen.findByText('Report not found')).toBeInTheDocument();
  });
});
