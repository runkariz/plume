import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { authStore } from '@/app/authStore';
import { renderApp } from '@/test/render';

describe('Maintainer sign-in', () => {
  it('shows the form with labelled fields and a Back to APIs link', () => {
    renderApp('/maintainer');
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Access token')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to APIs' })).toHaveAttribute('href', '/');
  });

  it('asks for a token when it is empty', async () => {
    renderApp('/maintainer');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your access token');
  });

  it('rejects a bad token with a clear message and stays signed out', async () => {
    renderApp('/maintainer');
    await userEvent.type(screen.getByLabelText('Access token'), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('That token was not accepted');
    expect(authStore.getKey()).toBeNull();
  });

  it('signs in with a valid token, shows the maintainer header, and keeps the key out of localStorage', async () => {
    renderApp('/maintainer');
    await userEvent.type(screen.getByLabelText('Email'), 'ada@example.com');
    await userEvent.type(screen.getByLabelText('Access token'), 'pl_secret123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Maintainer' })).toBeInTheDocument();
    expect(screen.getByText('ada')).toBeInTheDocument();
    expect(await screen.findByText('Shopify Admin REST')).toBeInTheDocument();
    expect(authStore.getKey()).toBe('pl_secret123');
    expect(JSON.stringify({ ...localStorage })).not.toContain('pl_secret123');
    // sessionStorage (this tab only) holds it under one key, so a refresh does not sign the person out
    expect(Object.keys(sessionStorage)).toEqual(['plume-maintainer-session']);
  });

  it('sign out clears the key and returns to the public home', async () => {
    authStore.signIn('pl_x', 'maintainer');
    renderApp('/maintainer');
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(authStore.getKey()).toBeNull();
    expect(await screen.findByText('Ask the docs,', { exact: false })).toBeInTheDocument();
  });

  it('protects wizard pages: redirects to sign-in, then back after signing in', async () => {
    renderApp('/maintainer/apis/shopify/update');
    expect(await screen.findByLabelText('Access token')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Access token'), 'pl_ok');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: /Update/ })).toBeInTheDocument();
  });
});
