import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { authStore } from '@/app/authStore';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { server, TEST_API_BASE } from '@/test/server';
import { ConsentChip, isConsentFilter, matchesConsent } from './consent';

beforeEach(() => {
  server.use(...createHandlers(TEST_API_BASE));
  authStore.signIn('pl_test_token_value');
});
afterEach(() => authStore.signOut());

describe('consent', () => {
  it('filters by method, by "no record", and lets everything through for all', () => {
    expect(matchesConsent({ consentMethod: 'elicitation' }, 'elicitation')).toBe(true);
    expect(matchesConsent({ consentMethod: 'llm_attested' }, 'elicitation')).toBe(false);
    expect(matchesConsent({ consentMethod: null }, 'none')).toBe(true);
    expect(matchesConsent({}, 'none')).toBe(true);
    expect(matchesConsent({ consentMethod: 'elicitation' }, 'none')).toBe(false);
    expect(matchesConsent({ consentMethod: 'something-new' }, 'all')).toBe(true);
    expect(isConsentFilter('llm_attested')).toBe(true);
    expect(isConsentFilter('x')).toBe(false);
  });

  it('shows the method as a chip, a method it does not know as written, and a missing one as "no record"', () => {
    const { rerender } = render(<ConsentChip method="elicitation" />);
    expect(screen.getByText('consent: elicitation')).toBeInTheDocument();
    rerender(<ConsentChip method="llm_attested" />);
    expect(screen.getByText('consent: assistant attested')).toBeInTheDocument();
    rerender(<ConsentChip method="future-method" />);
    expect(screen.getByText('consent: future-method')).toBeInTheDocument();
    rerender(<ConsentChip method={null} />);
    expect(screen.getByText('no consent record')).toBeInTheDocument();
  });
});

describe('on the reported questions pages', () => {
  it('a chip on each report and a filter in the URL', async () => {
    const { router } = renderApp('/maintainer/reports');
    const list = await screen.findByRole('list', { name: 'Reports' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('consent: elicitation');
    expect(within(list).getByText('no consent record')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Consent'), 'llm_attested');
    await waitFor(() => expect(router.state.location.search).toBe('?consent=llm_attested'));
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Reports' })).getAllByRole('listitem'),
      ).toHaveLength(1),
    );
    await userEvent.selectOptions(screen.getByLabelText('Consent'), 'none');
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Reports' })).getAllByRole('listitem'),
      ).toHaveLength(1),
    );
  });

  it('the report and each of its notes carry the chip', async () => {
    renderApp('/maintainer/reports/rq-1a2b3c4d5e');
    const notes = await screen.findByRole('list', { name: 'Notes on this report' });
    const items = within(notes).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('consent: elicitation');
    expect(items[1]).toHaveTextContent('consent: assistant attested');
    expect(screen.getAllByText('consent: elicitation').length).toBeGreaterThan(1); // the header too
  });
});

describe('on the mapping report pages', () => {
  it('a chip on each report and a filter in the URL', async () => {
    const { router } = renderApp('/maintainer/mapping-reports');
    const list = await screen.findByRole('list', { name: 'Mapping reports' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(6);
    expect(within(list).getByText('no consent record')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Consent'), 'llm_attested');
    await waitFor(() => expect(router.state.location.search).toBe('?consent=llm_attested'));
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'Mapping reports' })).getAllByRole('listitem'),
      ).toHaveLength(2),
    );
  });

  it('the report and its notes carry the chip', async () => {
    renderApp('/maintainer/mapping-reports/mr-1a2b3c4d5e');
    const notes = await screen.findByRole('list', { name: 'Notes on this report' });
    expect(within(notes).getAllByRole('listitem')[0]).toHaveTextContent('consent: elicitation');
    expect(screen.getAllByText('consent: elicitation').length).toBeGreaterThan(1);
  });
});
