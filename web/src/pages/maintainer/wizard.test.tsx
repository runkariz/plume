import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createHandlers } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { seedJob } from '@/test/jobs';
import { server, TEST_API_BASE } from '@/test/server';
import { authStore } from '@/app/authStore';

const zip = () => new File(['zip'], 'shopify-package.zip', { type: 'application/zip' });

describe('Upload step', () => {
  async function open() {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/apis/shopify/update');
    await screen.findByRole('heading', { name: /Update/ });
  }

  it('starts empty: breadcrumb, stepper at 1, fields disabled, Review disabled', async () => {
    await open();
    expect(screen.getByRole('link', { name: 'Maintainer' })).toBeInTheDocument();
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Upload');
    expect(screen.getByLabelText('API id')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeDisabled();
    expect(screen.getByText('Checks appear here once a package is chosen.')).toBeInTheDocument();
  });

  it('validates a chosen package and prefills the fields', async () => {
    await open();
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    expect(await screen.findByText('shopify-package.zip')).toBeInTheDocument();
    expect(screen.getByText('214 KB · 1,118 files')).toBeInTheDocument();
    expect(screen.getByText('Archive is safe')).toBeInTheDocument();
    expect(screen.getByText('0 blockers · 90 warnings · 24 notes')).toBeInTheDocument();
    expect(screen.getByLabelText('API id')).toHaveValue('shopify');
    expect(screen.getByLabelText('Display name')).toHaveValue('Shopify Admin REST');
    expect(screen.getByLabelText('Version tag')).toHaveValue('2026-11-14');
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeEnabled();
  });

  it('shows the server error for a rejected file', async () => {
    await open();
    await userEvent.upload(
      screen.getByLabelText('Choose package file'),
      new File(['x'], 'notes.txt', { type: 'text/plain' }),
      { applyAccept: false },
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Only .zip packages are accepted');
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeDisabled();
  });

  it('blocks the next step when a validation check fails', async () => {
    await open();
    server.use(
      http.post(`${TEST_API_BASE}/v1/packages`, async () => {
        const { sampleJob } = await import('@/mocks/jobData');
        const job = sampleJob();
        job.package.validation = [
          {
            key: 'archive',
            title: 'Archive is safe',
            detail: 'Path traversal in ../x',
            status: 'fail',
          },
        ];
        return HttpResponse.json(job, { status: 201 });
      }),
    );
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    expect(await screen.findByText('Path traversal in ../x')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeDisabled();
  });

  it('takes the API id from the package (read-only) and blocks a package for another API', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/apis/other-api/update');
    await screen.findByRole('heading', { name: /Update/ });
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This package is for “shopify”, not “other-api”',
    );
    expect(screen.getByLabelText('API id')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeDisabled();
  });

  it('a new API gets its id from the package', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/apis/new/update');
    await screen.findByRole('heading', { name: 'Add an API' });
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    await waitFor(() => expect(screen.getByLabelText('API id')).toHaveValue('shopify'));
    expect(screen.getByLabelText('API id')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Review changes →' })).toBeEnabled();
  });

  it('goes to the review step', async () => {
    await open();
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    await userEvent.click(await screen.findByRole('button', { name: 'Review changes →' }));
    expect(await screen.findByText('Embedding plan')).toBeInTheDocument();
  });

  it('shows a session error on 401', async () => {
    await open();
    authStore.signOut();
    authStore.signIn('bad', 'maintainer');
    await userEvent.upload(screen.getByLabelText('Choose package file'), zip());
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign in again');
  });
});

describe('Review step', () => {
  it('shows a loading state, then counts, the diff table, the plan and the banner', async () => {
    const id = await seedJob('reviewed');
    renderApp(`/maintainer/jobs/${id}/review`);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the review');
    expect(await screen.findByText('Embedding plan')).toBeInTheDocument();
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Review changes');
    expect(screen.getByText('38')).toBeInTheDocument();
    expect(screen.getByText('Unchanged, kept as is')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'What changed since 2026-11-02' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Showing 6 of 53')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Changed items' });
    expect(within(table).getAllByRole('row')).toHaveLength(7);
    expect(within(table).getByText('/admin/api/latest/gift_cards.json')).toBeInTheDocument();
    expect(screen.getByText('gemini-embedding-001')).toBeInTheDocument();
    expect(screen.getByText('Nothing goes live yet')).toBeInTheDocument();
    expect(screen.getByText(/Live search keeps using 2026-11-02/)).toBeInTheDocument();
  });

  it('shows an error for an unknown job', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/jobs/job-404/review');
    expect(await screen.findByRole('alert')).toHaveTextContent('Job not found');
  });

  it('redirects to the right step when the job is elsewhere', async () => {
    const id = await seedJob('staged');
    renderApp(`/maintainer/jobs/${id}/review`);
    expect(await screen.findByText('Evaluation, staged vs live')).toBeInTheDocument();
  });

  it('shows the empty-diff message', async () => {
    const id = await seedJob('reviewed');
    server.use(
      http.get(`${TEST_API_BASE}/v1/jobs/${id}`, async () => {
        const { sampleJob, withReview } = await import('@/mocks/jobData');
        const job = withReview(sampleJob({ id }));
        if (job.diff) {
          job.diff.items = [];
          job.diff.totalItems = 0;
        }
        return HttpResponse.json(job);
      }),
    );
    renderApp(`/maintainer/jobs/${id}/review`);
    expect(await screen.findByText(/No changes: every chunk is identical/)).toBeInTheDocument();
  });

  it('Start build moves to the build step', async () => {
    const id = await seedJob('reviewed');
    renderApp(`/maintainer/jobs/${id}/review`);
    await userEvent.click(await screen.findByRole('button', { name: 'Start build' }));
    expect(await screen.findByRole('heading', { name: 'Pipeline' })).toBeInTheDocument();
  });

  it('shows the error when the build cannot start', async () => {
    const id = await seedJob('reviewed');
    server.use(
      http.post(`${TEST_API_BASE}/v1/jobs/${id}/build`, () =>
        HttpResponse.json({ detail: 'A build is already running' }, { status: 409 }),
      ),
    );
    renderApp(`/maintainer/jobs/${id}/review`);
    await userEvent.click(await screen.findByRole('button', { name: 'Start build' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('A build is already running');
  });
});

describe('Build step', () => {
  it('streams events: steps complete, progress fills, services and log appear, continue unlocks', async () => {
    const id = await seedJob('building');
    renderApp(`/maintainer/jobs/${id}/build`);
    const next = await screen.findByRole('button', { name: 'Review quality gate →' });
    await waitFor(() => expect(next).toBeEnabled());
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Build');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('50 / 50')).toBeInTheDocument();
    expect(screen.getByText('pgvector 0.8 · 4 ms')).toBeInTheDocument();
    expect(screen.getByText('embedding-001 · 0 retries')).toBeInTheDocument();
    const pipeline = screen
      .getByRole('heading', { name: 'Pipeline' })
      .closest('div') as HTMLElement;
    expect(within(pipeline).getAllByText('(done)')).toHaveLength(6);
    expect(screen.getByRole('log').children.length).toBeGreaterThan(5);
    expect(screen.queryByText('Live')).not.toBeInTheDocument();
    await userEvent.click(next);
    expect(await screen.findByText('Quality gate passed')).toBeInTheDocument();
  });

  it('shows the failure, offers a retry and discard', async () => {
    server.use(...createHandlers(TEST_API_BASE, { failBuild: true }));
    const id = await seedJob('building');
    renderApp(`/maintainer/jobs/${id}/build`);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Embedding failed: Gemini quota exceeded.',
    );
    expect(screen.getByText('Batch 2 of 4 failed: quota exceeded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry build' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard build' }));
    expect(await screen.findByText('Build discarded')).toBeInTheDocument();
  });

  it('reports a lost connection and reconnects on demand', async () => {
    const id = await seedJob('building');
    let calls = 0;
    server.use(
      http.get(`${TEST_API_BASE}/v1/jobs/${id}/events`, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'proxy error' }, { status: 502 });
      }),
    );
    renderApp(`/maintainer/jobs/${id}/build`);
    expect(await screen.findByText('Lost the connection to the build')).toBeInTheDocument();
    expect(calls).toBe(6);
    server.resetHandlers();
    await userEvent.click(screen.getByRole('button', { name: 'Reconnect' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Review quality gate →' })).toBeEnabled(),
    );
  });

  it('shows the loading state first and an error for an unknown job', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/jobs/job-404/build');
    expect(screen.getByRole('status')).toHaveTextContent('Loading the build');
    expect(await screen.findByRole('alert')).toHaveTextContent('Job not found');
  });

  it('redirects a not-yet-started job back to review', async () => {
    const id = await seedJob('reviewed');
    renderApp(`/maintainer/jobs/${id}/build`);
    expect(await screen.findByText('Embedding plan')).toBeInTheDocument();
  });
});

describe('Publish step', () => {
  it('shows the gate, metrics, release info and publishes', async () => {
    const id = await seedJob('staged');
    renderApp(`/maintainer/jobs/${id}/publish`);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the quality gate');
    expect(await screen.findByText('Quality gate passed')).toBeInTheDocument();
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Publish');
    const table = screen.getByRole('table');
    expect(within(table).getByText('Recall@5')).toBeInTheDocument();
    expect(within(table).getAllByText('+0.01').length).toBeGreaterThan(0);
    // per question source, from the same metrics list
    expect(within(table).getByText('Recall@5 (docs questions)')).toBeInTheDocument();
    expect(within(table).getByText('Recall@5 (spec questions)')).toBeInTheDocument();
    expect(screen.getByText('shopify-2026-11-14.dump.gz')).toBeInTheDocument();
    expect(screen.getByText('Switch live search to the staged build')).toBeInTheDocument();
    expect(screen.getByText('Move the tag “latest” to it')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Publish 2026-11-14' }));
    expect(await screen.findByText('Published 2026-11-14')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View Shopify Admin REST' })).toHaveAttribute(
      'href',
      '/apis/shopify',
    );
  });

  it('lets you publish when no gold set exists (eval is null) and says the gate did not run', async () => {
    const id = await seedJob('staged');
    server.use(
      http.get(`${TEST_API_BASE}/v1/jobs/${id}`, async () => {
        const { sampleJob } = await import('@/mocks/jobData');
        return HttpResponse.json(
          sampleJob({
            id,
            status: 'staged',
            stagedBuild: 'b-6ff6063a275d40c14e4bcdd001f1c9ae',
            eval: null,
          }),
        );
      }),
    );
    renderApp(`/maintainer/jobs/${id}/publish`);
    expect(await screen.findByText('No quality gate ran')).toBeInTheDocument();
    expect(screen.getByText(/Add a gold question set/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish b-6ff6063a275d' })).toBeEnabled();
    expect(screen.getByText('b-6ff6063a275d40c14e4bcdd001f1c9ae')).toBeInTheDocument();
  });

  it('blocks publishing when the gate failed', async () => {
    server.use(...createHandlers(TEST_API_BASE, { failGate: true }));
    const id = await seedJob('staged');
    renderApp(`/maintainer/jobs/${id}/publish`);
    expect(await screen.findByText('Quality gate failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish 2026-11-14' })).toBeDisabled();
    expect(screen.getByText('-0.12')).toBeInTheDocument();
  });

  it('asks before discarding, then shows the discarded state', async () => {
    const id = await seedJob('staged');
    renderApp(`/maintainer/jobs/${id}/publish`);
    await userEvent.click(await screen.findByRole('button', { name: 'Discard build' }));
    await userEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(screen.getByRole('button', { name: 'Discard build' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard build' }));
    await userEvent.click(screen.getByRole('button', { name: 'Yes, discard' }));
    expect(await screen.findByText('Build discarded')).toBeInTheDocument();
  });

  it('downloads the dump', async () => {
    const id = await seedJob('staged');
    const create = vi.fn(() => 'blob:x');
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    renderApp(`/maintainer/jobs/${id}/publish`);
    await userEvent.click(await screen.findByRole('button', { name: 'Download dump' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(create).toHaveBeenCalled();
    click.mockRestore();
  });

  it('shows an error when publishing is refused', async () => {
    const id = await seedJob('staged');
    server.use(
      http.post(`${TEST_API_BASE}/v1/jobs/${id}/publish`, () =>
        HttpResponse.json({ detail: 'The quality gate has not passed' }, { status: 409 }),
      ),
    );
    renderApp(`/maintainer/jobs/${id}/publish`);
    await userEvent.click(await screen.findByRole('button', { name: 'Publish 2026-11-14' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('quality gate has not passed');
  });

  it('shows an error for an unknown job', async () => {
    authStore.signIn('pl_ok', 'maintainer');
    renderApp('/maintainer/jobs/job-404/publish');
    expect(await screen.findByRole('alert')).toHaveTextContent('Job not found');
  });
});
