import { screen } from '@testing-library/react';
import { renderApp } from '@/test/render';
import { GITHUB_URL } from './Layout';

describe('the GitHub link in the header', () => {
  it('goes to the project repository and opens in a new tab, without handing the page to the new tab', async () => {
    renderApp('/');
    const link = await screen.findByRole('link', { name: 'GitHub' });
    expect(GITHUB_URL).toBe('https://github.com/runkariz/plume');
    expect(link).toHaveAttribute('href', 'https://github.com/runkariz/plume');
    expect(link).toHaveAttribute('target', '_blank');
    const rel = (link.getAttribute('rel') ?? '').split(/\s+/);
    expect(rel).toContain('noopener');
    expect(rel).toContain('noreferrer');
  });
});
