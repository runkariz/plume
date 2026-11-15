import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import type { EndpointRefs, TriggerSummary } from '@/api/types';
import { Button, Card, Chip, EmptyState, ErrorState, LoadingState } from '@/components';
import { EndpointRef } from './EndpointRef';
import { WebhookMechanism } from './WebhookMechanism';

const PAGE = 50;

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | {
      status: 'ready';
      present: boolean;
      note: string | null;
      total: number;
      items: TriggerSummary[];
      webhooks: Record<string, unknown>[];
      refs: EndpointRefs;
    };

/**
 * The trigger / webhook events of the package, page by page, and the webhook delivery mechanism when the package
 * has one. Nothing in the package: a clear "Not in this package".
 */
export function TriggersPanel({ apiId }: { apiId: string }) {
  const client = useApiClient();
  const [state, setState] = useState<State>({ status: 'loading' });
  const [more, setMore] = useState<'idle' | 'loading' | 'error'>('idle');
  const [query, setQuery] = useState('');

  useEffect(() => {
    const ctrl = new AbortController();
    client.getTriggers(apiId, { limit: PAGE }, ctrl.signal).then(
      (r) =>
        setState({
          status: 'ready',
          present: r.present,
          note: r.note,
          total: r.total,
          items: r.items,
          webhooks: r.webhooks ?? [],
          refs: r.endpointRefs ?? {},
        }),
      (e: unknown) => {
        if (!ctrl.signal.aborted)
          setState({
            status: 'error',
            message: e instanceof Error ? e.message : 'Could not load the triggers.',
          });
      },
    );
    return () => ctrl.abort();
  }, [client, apiId]);

  async function loadMore() {
    if (state.status !== 'ready') return;
    setMore('loading');
    try {
      const r = await client.getTriggers(apiId, { limit: PAGE, offset: state.items.length });
      setState({ ...state, total: r.total, items: [...state.items, ...r.items] });
      setMore('idle');
    } catch {
      setMore('error');
    }
  }

  const q = query.trim().toLowerCase();
  const shown =
    state.status === 'ready'
      ? state.items.filter(
          (t) =>
            !q || `${t.title} ${t.description ?? ''} ${t.resource ?? ''}`.toLowerCase().includes(q),
        )
      : [];

  return (
    <>
      {state.status === 'ready'
        ? state.webhooks.map((m, i) => (
            <WebhookMechanism
              key={String(m.id ?? i)}
              apiId={apiId}
              mechanism={m}
              refs={state.refs}
            />
          ))
        : null}
      <Card className="pad" role="region" aria-label="Triggers and webhooks">
        <h2 className="h2-sm">Triggers and webhooks</h2>
        {state.status === 'loading' ? <LoadingState label="Loading triggers" /> : null}
        {state.status === 'error' ? (
          <ErrorState title="Could not load triggers" message={state.message} />
        ) : null}
        {state.status === 'ready' && !state.present ? (
          <EmptyState title="Not in this package">
            {state.note
              ? `The package has no triggers or webhooks (${state.note}).`
              : 'The package documents no trigger events.'}
          </EmptyState>
        ) : null}
        {state.status === 'ready' && state.present && state.total === 0 ? (
          <EmptyState title="No events listed">
            The package describes how events are delivered, but lists no trigger events.
          </EmptyState>
        ) : null}
        {state.status === 'ready' && state.present && state.total > 0 ? (
          <>
            <div className="searchbar" style={{ marginBottom: 6 }}>
              <input
                type="search"
                aria-label="Filter events"
                placeholder={`Filter the ${state.items.length} loaded events`}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="faint small" aria-live="polite">
              {shown.length} of {state.total} events{q ? ' match' : ''}
            </p>
            {shown.length === 0 ? (
              <EmptyState title="No event matches">Try other words.</EmptyState>
            ) : (
              <ul className="sec-list">
                {shown.map((t) => (
                  <li key={t.docId} className="sec-item">
                    <div className="sec-main">
                      <Link
                        className="sec-link mono"
                        to={`/apis/${encodeURIComponent(apiId)}/triggers/${encodeURIComponent(t.key ?? t.docId)}`}
                      >
                        {t.title}
                      </Link>
                      {t.description ? <div className="muted small">{t.description}</div> : null}
                      {t.syncEndpointId ? (
                        <div className="muted small">
                          Polled via{' '}
                          <EndpointRef
                            apiId={apiId}
                            endpointId={t.syncEndpointId}
                            refs={state.refs}
                          />
                        </div>
                      ) : null}
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      {t.resource ? <Chip>{t.resource}</Chip> : null}
                      {t.delivery ? <Chip tone="info">{t.delivery}</Chip> : null}
                      {t.syncEndpointId ? (
                        <span title={t.syncEndpointId}>
                          <Chip>polled</Chip>
                        </span>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {state.items.length < state.total ? (
              <div className="show-all">
                <Button disabled={more === 'loading'} onClick={() => void loadMore()}>
                  {more === 'loading'
                    ? 'Loading…'
                    : `Show more (${state.total - state.items.length} left)`}
                </Button>
                {more === 'error' ? (
                  <p role="alert" className="form-error">
                    Could not load more events.
                  </p>
                ) : null}
              </div>
            ) : null}
          </>
        ) : null}
      </Card>
    </>
  );
}
