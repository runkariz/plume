import { Link, NavLink, Outlet } from 'react-router-dom';
import { GitHubIcon, MoonIcon, PlumeMark, SunIcon } from '@/icons';
import { Button } from '@/components';
import { useTheme } from './theme';

export const GITHUB_URL = 'https://github.com/';

export function Layout() {
  const { theme, toggle } = useTheme();
  return (
    <>
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
            <NavLink to="/maintainer" tabIndex={-1}>
              <Button>Maintainer</Button>
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="wrap">
        <Outlet />
      </main>
    </>
  );
}
