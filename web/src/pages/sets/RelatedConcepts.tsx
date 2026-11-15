import { useCallback, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import {
  ApiError,
  type ApiRef,
  type RelatedAlias,
  type RelatedConcept,
  type RelatedEvidence,
  type SetAlias,
  type SetSessionRequest,
  type SetSessionResponse,
} from '@/api/types';
import { useIsMaintainer, useServerGeneration } from '@/app/authStore';
import {
  ApiAvatar,
  Banner,
  Button,
  Card,
  Chip,
  Crumbs,
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components';
import { SetJobProgress, SetSessionPanel } from './SetCreate';

const KIND_WORD = {
  nested: 'nested objects',
  sub_resource: 'sub-resource',
  id_field: 'id field',
  model_ref: 'model reference',
} as const;

/** At most 8 members in a set (the root and up to 7 related). */
const MAX_MEMBERS = 8;

/** Where the docs of one API show the connection: what kind, the quote, the paths, the endpoint. Plain text. */
function EvidenceList({
  evidence,
  apis,
}: {
  evidence: Record<string, RelatedEvidence[]>;
  apis: ApiRef[];
}) {
  return (
    <ul className="related-evidence plain">
      {apis
        .filter((a) => (evidence[a.id] ?? []).length > 0)
        .map((a) => (
          <li key={a.id}>
            <div className="related-api">
              <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={18} />
              <b>{a.shortName}</b>
            </div>
            <ul className="plain">
              {(evidence[a.id] ?? []).map((e, n) => (
                <li key={`${e.kind}-${e.paths.join()}-${n}`}>
                  <Chip>{KIND_WORD[e.kind]}</Chip>{' '}
                  <span className="mono small">{e.paths.join(', ')}</span>
                  {e.fetch ? <div className="mono small faint">{e.fetch}</div> : null}
                  <blockquote className="quote small">{e.quote}</blockquote>
                </li>
              ))}
            </ul>
          </li>
        ))}
    </ul>
  );
}

function RelatedRow({
  item,
  apis,
  checked,
  disabled,
  note,
  onToggle,
}: {
  item: RelatedConcept;
  apis: ApiRef[];
  checked: boolean;
  disabled: boolean;
  /** "Same as Variant" for the second name of an accepted alias. */
  note: string | null;
  onToggle: () => void;
}) {
  const inputId = `related-${item.id}`;
  const evidence: Record<string, RelatedEvidence[]> = {};
  for (const c of item.candidates)
    for (const [api, list] of Object.entries(c.sources))
      evidence[api] = [...(evidence[api] ?? []), ...list];
  const total = Object.values(evidence).reduce((n, l) => n + l.length, 0);
  // the designs the docs support, in words (the person picks one later, in the set)
  const designs = [
    ...new Set(
      item.candidates.flatMap((c) =>
        c.options.map((o) =>
          o.kind === 'embedded'
            ? `${c.child.name} inside ${c.parent.name} (${o.cardinality})`
            : `${c.child.name} refers to ${c.parent.name} (${o.cardinality})`,
        ),
      ),
    ),
  ];
  return (
    <li className={`card related${checked ? ' on' : ''}`}>
      <div className="related-main">
        <input
          id={inputId}
          type="checkbox"
          className="check"
          checked={checked}
          disabled={disabled}
          onChange={onToggle}
        />
        <label htmlFor={inputId} className="related-name">
          <h3>{item.name}</h3>
        </label>
        <span className="related-kinds">
          {apis.map((a) => {
            const kinds = item.kinds[a.id] ?? [];
            return (
              <span key={a.id} className={`related-kind${kinds.length ? '' : ' none'}`}>
                <ApiAvatar
                  text={a.logo.text}
                  color={a.logo.color}
                  url={a.logo.url}
                  size={20}
                  kind={kinds.length ? 'direct' : 'absent'}
                />
                <span className="small">
                  {a.shortName}:{' '}
                  {kinds.length ? kinds.map((k) => KIND_WORD[k]).join(', ') : 'not documented'}
                </span>
              </span>
            );
          })}
        </span>
      </div>
      {note ? <p className="small muted related-note">{note}</p> : null}
      {designs.length ? (
        <p className="small muted related-designs">The docs support: {designs.join('; ')}</p>
      ) : null}
      {total > 0 ? (
        <details className="related-details">
          <summary>Evidence in the docs ({total})</summary>
          <EvidenceList evidence={evidence} apis={apis} />
        </details>
      ) : null}
    </li>
  );
}

function aliasKey(a: RelatedAlias) {
  return Object.values(a.names)
    .map((n) => n.id)
    .sort()
    .join('|');
}

/**
 * "Related concepts" of one concept (Product → Variant, Image, …): what the docs of the chosen APIs connect to it, each
 * with its evidence per API. The person picks the ones to model together and creates a model set: with Claude (a set
 * session) or, for a signed-in maintainer when the server can generate, on the server. A pair that is named differently
 * in the APIs (variant / variation) is offered as an alias: the person decides whether it is one concept.
 */
export function RelatedConcepts() {
  const client = useApiClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const key = (params.get('apis') ?? '').split(',').filter(Boolean).join(',');
  const apiIds = useMemo(() => (key === '' ? [] : key.split(',')), [key]);
  const concept = params.get('concept') ?? '';
  const maintainer = useIsMaintainer();
  const serverGeneration = useServerGeneration();

  const load = useCallback(
    (signal: AbortSignal) =>
      apiIds.length >= 2 && concept
        ? client.suggestRelated({ apis: apiIds, concept }, signal)
        : Promise.resolve(null),
    [client, apiIds, concept],
  );
  const { state, retry } = useAsync(load);
  const first = state.status === 'ready' ? state.data : null;

  // further pages
  const [more, setMore] = useState<{ items: RelatedConcept[]; next: number | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  async function showMore() {
    const next = more ? more.next : (first?.nextOffset ?? null);
    if (next === null) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const r = await client.suggestRelated({ apis: apiIds, concept, offset: next });
      setMore({ items: [...(more?.items ?? []), ...r.related], next: r.nextOffset });
    } catch (e) {
      setMoreError(e instanceof Error ? e.message : 'Could not load more.');
    } finally {
      setLoadingMore(false);
    }
  }
  const items = useMemo(() => [...(first?.related ?? []), ...(more?.items ?? [])], [first, more]);
  const nextOffset = more ? more.next : (first?.nextOffset ?? null);

  const [picked, setPicked] = useState<string[]>([]);
  const [accepted, setAccepted] = useState<string[]>([]);
  const aliases = first?.aliases ?? [];
  // the first chosen API's name stands for an accepted alias
  const canonicalId = (a: RelatedAlias) =>
    a.names[apiIds[0] ?? '']?.id ?? Object.values(a.names)[0]?.id ?? '';
  const canonicalName = (a: RelatedAlias) =>
    a.names[apiIds[0] ?? '']?.name ?? Object.values(a.names)[0]?.name ?? '';
  const groupOf = (id: string) =>
    aliases.find(
      (a) => accepted.includes(aliasKey(a)) && Object.values(a.names).some((n) => n.id === id),
    );
  const keyOf = (id: string) => {
    const g = groupOf(id);
    return g ? canonicalId(g) : id;
  };
  const nameOf = (id: string) => items.find((r) => r.id === id)?.name ?? id;
  function toggle(id: string) {
    const k = keyOf(id);
    setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  }
  function setAlias(a: RelatedAlias, on: boolean) {
    const k = aliasKey(a);
    const ids = Object.values(a.names).map((n) => n.id);
    const canon = canonicalId(a);
    setAccepted((cur) => (on ? [...cur, k] : cur.filter((x) => x !== k)));
    // either name picked before: the one concept stays picked, under its common name
    setPicked((p) => {
      const any = p.some((x) => ids.includes(x));
      const rest = p.filter((x) => !ids.includes(x));
      return any ? [...rest, canon] : rest;
    });
  }

  const [session, setSession] = useState<{
    response: SetSessionResponse;
    concepts: string[];
  } | null>(null);
  const [job, setJob] = useState<{ jobId: string; concepts: string[] } | null>(null);
  const [busy, setBusy] = useState<'claude' | 'server' | null>(null);
  const [error, setError] = useState<{ message: string; claudeFallback: boolean } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const rootName = first?.concept.name ?? concept;
  const members = [rootName, ...picked.map((id) => nameOf(id))];
  const memberAliases: SetAlias[] = aliases
    .filter((a) => accepted.includes(aliasKey(a)) && picked.includes(canonicalId(a)))
    .map((a) => ({
      concept: canonicalName(a),
      names: Object.fromEntries(Object.entries(a.names).map(([api, n]) => [api, n.name])),
    }));
  const full = members.length >= MAX_MEMBERS;

  const open = useCallback(
    (setId: string, extra?: { ownerKey?: string }) =>
      navigate(
        `/model-sets/${setId}`,
        extra?.ownerKey ? { state: { ownerKey: extra.ownerKey } } : undefined,
      ),
    [navigate],
  );

  async function create(engine: 'claude' | 'server') {
    setError(null);
    setBusy(engine);
    const req: SetSessionRequest = {
      apis: apiIds,
      concepts: members,
      ...(memberAliases.length ? { aliases: memberAliases } : {}),
    };
    try {
      if (engine === 'server') {
        const r = await client.generateModelSet(req);
        setJob({ jobId: r.jobId, concepts: members });
        setSession(null);
      } else {
        const r = await client.startSetSession(req);
        setSession({ response: r, concepts: members });
        setJob(null);
      }
      setTimeout(
        () => panelRef.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' }),
        0,
      );
    } catch (e) {
      setError({
        message:
          e instanceof ApiError && e.code === 'llm_unavailable'
            ? 'Server-side generation is not configured on this Plume. You can create the set with Claude instead.'
            : e instanceof ApiError && e.status === 401
              ? 'Your session is not valid any more. Sign in again, or create the set with Claude.'
              : e instanceof ApiError && e.status === 429
                ? 'Too many requests right now. Try again in a minute.'
                : e instanceof Error
                  ? e.message
                  : 'Could not create the set.',
        claudeFallback: engine === 'server',
      });
    } finally {
      setBusy(null);
    }
  }

  const crumbs = [
    { label: 'APIs', to: '/' },
    { label: 'Create a model', to: `/models?apis=${key}` },
    { label: 'Suggestions', to: `/models/suggest?apis=${key}` },
    { label: 'Related concepts' },
  ];

  if (apiIds.length < 2 || !concept)
    return (
      <>
        <Crumbs items={crumbs.slice(0, 2)} />
        <EmptyState title="Pick a concept first">
          <Link to="/models">Choose the APIs and a concept</Link>
        </EmptyState>
      </>
    );

  // unknown (null) = try the server, like the suggestions page; false = it said it has no model key
  const canServer = maintainer && serverGeneration !== false;
  const disabled = busy !== null || members.length < 2;

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">Concepts related to {rootName}</h1>
          {first ? (
            <ul className="selbar-chips plain" aria-label="Selected APIs">
              {first.apis.map((a) => (
                <li key={a.id} className="selbar-chip light">
                  <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={26} />
                  {a.shortName}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <Link className="btn" to={`/models/suggest?apis=${key}`}>
          Back to suggestions
        </Link>
      </div>
      <p className="muted">
        Taken only from what the docs of these APIs say: nested objects, sub-resource paths, id
        fields that name {rootName}, and model references. Pick the concepts to model together with{' '}
        {rootName}; you decide how each relation is designed afterwards.
      </p>
      {state.status === 'loading' ? <LoadingState label="Looking through the docs" /> : null}
      {state.status === 'error' ? (
        <ErrorState
          title="Could not find related concepts"
          message={state.error.message}
          onRetry={retry}
        />
      ) : null}
      {first ? (
        <>
          {aliases.length ? (
            <section aria-label="Same thing, different names?" className="related-aliases">
              <h2 className="h2-sm">Same thing, different names?</h2>
              {aliases.map((a) => {
                const k = aliasKey(a);
                const on = accepted.includes(k);
                const names = Object.entries(a.names);
                const label = names.map(([, n]) => n.name).join(' and ');
                return (
                  <Card key={k} className="pad related-alias">
                    <p>
                      {names.map(([api, n], i) => (
                        <span key={api}>
                          {i > 0 ? ' and ' : ''}
                          <b>{n.name}</b> ({first.apis.find((x) => x.id === api)?.shortName ?? api})
                        </span>
                      ))}{' '}
                      sit at the same place under {a.parent.name}. The docs do not say they are the
                      same thing: you decide.
                    </p>
                    <EvidenceList
                      evidence={Object.fromEntries(
                        Object.entries(a.evidence).map(([api, e]) => [api, [e]]),
                      )}
                      apis={first.apis}
                    />
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={(e) => setAlias(a, e.target.checked)}
                      />
                      <span>
                        Treat {label} as one concept
                        {on ? <> (called {canonicalName(a)})</> : null}
                      </span>
                    </label>
                  </Card>
                );
              })}
            </section>
          ) : null}
          {items.length === 0 ? (
            <EmptyState title={`No related concepts found for ${rootName}`}>
              The docs of these APIs do not connect {rootName} to another concept in a way Plume can
              cite.
            </EmptyState>
          ) : (
            <ul className="plain related-list" aria-label="Related concepts">
              {items.map((r) => {
                const g = groupOf(r.id);
                const canon = g ? canonicalId(g) : r.id;
                const second = g !== undefined && canon !== r.id;
                return (
                  <RelatedRow
                    key={r.id}
                    item={r}
                    apis={first.apis}
                    checked={picked.includes(canon)}
                    disabled={busy !== null || (!picked.includes(canon) && full)}
                    note={
                      second && g ? `Same concept as ${canonicalName(g)} (you accepted it).` : null
                    }
                    onToggle={() => toggle(r.id)}
                  />
                );
              })}
            </ul>
          )}
          {nextOffset !== null ? (
            <div className="row">
              <Button onClick={() => void showMore()} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : 'Show more'}
              </Button>
              {moreError ? (
                <span role="alert" className="form-error">
                  {moreError}
                </span>
              ) : null}
            </div>
          ) : null}
          <Card className="pad set-bar" role="region" aria-label="Create a model set">
            <div className="set-bar-main">
              <div>
                <h2 className="h2-sm">Your model set</h2>
                <p className="muted small" aria-live="polite">
                  {members.length < 2
                    ? `${rootName} alone is not a set: pick at least one related concept.`
                    : `${members.length} models: ${members.join(', ')}`}
                  {full ? ` (the most a set can have is ${MAX_MEMBERS})` : ''}
                </p>
              </div>
              <div className="set-bar-actions">
                {canServer ? (
                  <>
                    <Button
                      variant="primary"
                      disabled={disabled}
                      onClick={() => void create('server')}
                    >
                      {busy === 'server' ? 'Starting…' : 'Generate the set'}
                    </Button>
                    <button
                      type="button"
                      className="linkbtn small"
                      disabled={disabled}
                      onClick={() => void create('claude')}
                    >
                      Use Claude instead
                    </button>
                  </>
                ) : (
                  <Button
                    variant="primary"
                    disabled={disabled}
                    onClick={() => void create('claude')}
                  >
                    {busy === 'claude' ? 'Starting…' : 'Create with Claude'}
                  </Button>
                )}
              </div>
            </div>
            {maintainer && serverGeneration === false ? (
              <p className="faint small">
                Server-side generation is not configured on this Plume, so the set is created with
                Claude.
              </p>
            ) : null}
            {memberAliases.length ? (
              <p className="faint small">
                {memberAliases
                  .map((a) => `${a.concept}: ${Object.values(a.names).join(' = ')}`)
                  .join('; ')}{' '}
                (accepted as one concept)
              </p>
            ) : null}
          </Card>
          <div ref={panelRef} className="concept-panels" tabIndex={-1}>
            {error ? (
              <Banner tone="bad" title="The set was not started">
                <span>{error.message}</span>
                {error.claudeFallback ? (
                  <div className="row" style={{ marginTop: 10 }}>
                    <Button onClick={() => void create('claude')}>
                      Create with Claude instead
                    </Button>
                  </div>
                ) : null}
              </Banner>
            ) : null}
            {job ? (
              <SetJobProgress
                key={job.jobId}
                jobId={job.jobId}
                concepts={job.concepts}
                onOpen={open}
                onCancel={() => setJob(null)}
                onUseClaude={() => {
                  setJob(null);
                  void create('claude');
                }}
              />
            ) : null}
            {session ? (
              <SetSessionPanel
                key={session.response.setSessionId}
                session={session.response}
                concepts={session.concepts}
                onOpen={open}
                onCancel={() => setSession(null)}
              />
            ) : null}
          </div>
        </>
      ) : null}
    </>
  );
}
