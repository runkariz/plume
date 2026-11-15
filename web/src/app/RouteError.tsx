import { useEffect } from 'react';
import { isRouteErrorResponse, useRouteError } from 'react-router-dom';
import { isChunkLoadError, reloadOnce } from './chunkReload';

/**
 * What a person sees when a page crashes or cannot load, instead of React Router's developer screen. A failed lazy
 * chunk (a new version was deployed under an open tab) reloads once by itself; if that does not help, the page says
 * a new version is out and offers Reload. Technical details stay behind a disclosure, as plain text.
 */
export function RouteError() {
  const error = useRouteError();
  const stale = isChunkLoadError(error);
  useEffect(() => {
    if (stale) reloadOnce();
  }, [stale]);
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : null;
  return (
    <div role="alert" className="state error route-error">
      <h3>{stale ? 'A new version of Plume is available' : 'Something went wrong'}</h3>
      <p>
        {stale
          ? 'This page was opened before an update. Reload to get the new version.'
          : 'The page could not be shown. Reloading often helps; if it does not, go back to the home page.'}
      </p>
      <div className="row" style={{ justifyContent: 'center' }}>
        <button type="button" className="btn primary" onClick={() => window.location.reload()}>
          Reload
        </button>
        {/* a plain link: a full load of the home page works even when the router is what failed */}
        <a className="btn" href="/">
          Home
        </a>
      </div>
      {detail ? (
        <details className="faint small">
          <summary>Details</summary>
          <p className="mono">{detail}</p>
        </details>
      ) : null}
    </div>
  );
}

/** The same, for a failure of the whole layout: no header to rely on, so it stands on its own. */
export function RootError() {
  return (
    <main className="wrap" id="main">
      <RouteError />
    </main>
  );
}
