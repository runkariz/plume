import { useCallback, useEffect, useState } from 'react';

export type AsyncState<T> =
  { status: 'loading' } | { status: 'error'; error: Error } | { status: 'ready'; data: T };

/** Runs `load` on mount and whenever it changes; `retry()` runs it again. Aborts on unmount. */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset to loading on (re)load
    setState({ status: 'loading' });
    load(ctrl.signal).then(
      (data) => {
        if (!ctrl.signal.aborted) setState({ status: 'ready', data });
      },
      (error: unknown) => {
        if (!ctrl.signal.aborted)
          setState({
            status: 'error',
            error: error instanceof Error ? error : new Error(String(error)),
          });
      },
    );
    return () => ctrl.abort();
  }, [load, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, retry };
}
