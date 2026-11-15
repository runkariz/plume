import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { ApiError } from '@/api/types';
import { authStore, useIsMaintainer } from '@/app/authStore';
import { Button, Card, Field } from '@/components';
import { PlumeMark } from '@/icons';

export function SignInPage() {
  const client = useApiClient();
  const navigate = useNavigate();
  const location = useLocation();
  const signedIn = useIsMaintainer();
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = (location.state as { next?: string } | null)?.next ?? '/maintainer';

  if (signedIn) return <Navigate to={next} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) {
      setError('Enter your access token.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const who = await client.verifyMaintainer(token.trim());
      const name = email.trim() ? (email.trim().split('@')[0] ?? who.name) : who.name;
      authStore.signIn(token.trim(), name || who.name);
      navigate(next, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'That token was not accepted.'
          : err instanceof Error
            ? err.message
            : 'Could not sign in.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <Card className="login">
        <div className="login-brand">
          <PlumeMark /> Plume
        </div>
        <h1 className="sr-only">Maintainer sign-in</h1>
        <p className="muted login-lead">
          Maintainer sign-in. Everyone can read; only maintainers upload packages and publish
          knowledge.
        </p>
        <form onSubmit={submit} noValidate>
          <Field
            label="Email"
            type="email"
            autoComplete="username"
            placeholder="maintainer@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            label="Access token"
            type="password"
            mono
            autoComplete="current-password"
            placeholder="pl_…"
            hint="Tokens are issued by project maintainers. It is kept in memory only."
            value={token}
            onChange={(e) => setToken(e.target.value)}
            aria-invalid={error ? true : undefined}
          />
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
          <Button variant="primary" size="lg" type="submit" className="block" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Card>
    </div>
  );
}
