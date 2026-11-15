import { Link, NavLink, Outlet, useLocation, useMatches, useNavigate } from 'react-router-dom';
import { GitHubIcon, MoonIcon, PlumeMark, SunIcon } from '@/icons';
import { authStore, useIsMaintainer, useMaintainerName } from './authStore';
import { useTheme } from './theme';

export const GITHUB_URL = 'https://github.com/';

export function Layout() {
  const { theme, toggle } = useTheme();
  const maintainer = useIsMaintainer();
  const name = useMaintainerName() ?? 'maintainer';
  const wide = useMatches().some((m) => (m.handle as { wide?: boolean } | undefined)?.wide);
  const onSignIn = useLocation().pathname === '/maintainer';
  const navigate = useNavigate();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="wrap">
          <Link to="/" className="brand" aria-label="Plume home">
            <PlumeMark /> Plume
          </Link>
          <nav className="site-nav" aria-label="Main">
            <button
              type="button"
              className="nav-link"
              onClick={toggle}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            </button>
            <NavLink className="nav-link" to="/models">
              Models
            </NavLink>
            <a className="nav-link" href={GITHUB_URL} rel="noreferrer">
              <GitHubIcon /> <span className="nav-text">GitHub</span>
            </a>
            {maintainer ? (
              <>
                <span className="chip acc">Maintainer</span>
                <span className="user">
                  <span className="avatar" aria-hidden>
                    {name.charAt(0).toUpperCase()}
                  </span>
                  <span className="nav-text">{name}</span>
                </span>
                <button
                  type="button"
                  className="nav-link strong"
                  onClick={() => {
                    authStore.signOut();
                    navigate('/');
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <Link className="btn" to={onSignIn ? '/' : '/maintainer'}>
                {onSignIn ? 'Back to APIs' : 'Maintainer'}
              </Link>
            )}
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className={wide ? 'wrap wide' : 'wrap'}>
        <Outlet />
      </main>
    </>
  );
}
