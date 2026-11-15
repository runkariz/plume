import { useCallback } from 'react';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { Card, Chip, EmptyState, ErrorState, LoadingState } from '@/components';

/** W1 placeholder: proves client + mocks + states end to end. Replaced by the real Home in W2. */
export function HomeStub() {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.listApis(signal), [client]);
  const { state, retry } = useAsync(load);

  return (
    <section className="section">
      <div className="eyebrow">Open knowledge bases for APIs</div>
      <h1>
        Ask the docs,
        <br />
        <em>not the internet.</em>
      </h1>
      <div className="section">
        {state.status === 'loading' ? <LoadingState label="Loading APIs" /> : null}
        {state.status === 'error' ? (
          <ErrorState title="Could not load APIs" message={state.error.message} onRetry={retry} />
        ) : null}
        {state.status === 'ready' && state.data.items.length === 0 ? (
          <EmptyState title="No APIs yet">Published knowledge bases will show up here.</EmptyState>
        ) : null}
        {state.status === 'ready' && state.data.items.length > 0 ? (
          <ul className="kit-grid" style={{ listStyle: 'none' }}>
            {state.data.items.map((a) => (
              <li key={a.id}>
                <Card className="pad">
                  <h3>{a.name}</h3>
                  <p className="muted">{a.category}</p>
                  <Chip tone="ok" dot>
                    {a.endpoints} endpoints
                  </Chip>
                </Card>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
