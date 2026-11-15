import { Link, Outlet, useNavigate } from 'react-router-dom';
import { GitHubIcon, MoonIcon, PlumeMark, SunIcon } from '@/icons';
import { authStore, useIsMaintainer } from './authStore';
import { useTheme } from './theme';

export const GITHUB_URL = 'https://github.com/';

export function Layout() {
  const { theme, toggle } = useTheme();
  const maintainer = useIsMaintainer();
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
            <a className="nav-link" href={GITHUB_URL} rel="noreferrer">
              <GitHubIcon /> GitHub
            </a>
            {maintainer ? (
              <>
                <span className="chip acc">Maintainer</span>
                <span className="user">
                  <span className="avatar" aria-hidden>
                    M
                  </span>
                  maintainer
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
              <Link className="btn" to="/maintainer">
                Maintainer
              </Link>
            )}
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="wrap">
        <Outlet />
      </main>
    </>
  );
}
