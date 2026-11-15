import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type DraftIssue, type ModelSet } from '@/api/types';
import { useIsMaintainer } from '@/app/authStore';
import { Banner, Button, Card, Chip, Crumbs, ErrorState, LoadingState } from '@/components';
import { docHref } from '@/lib/docHref';
import { richText } from '@/lib/richText';
import { saveOwnerKey } from '@/lib/ownerKeys';
import {
  LineageHistory,
  LineageLine,
  OwnerKeyNotice,
  ReviseCard,
  ShareCard,
  VisibilityChip,
} from '@/pages/models/ModelAccess';
import { StaleChip } from '@/pages/models/StaleChip';
import { SetDetail, editsFor, optionText, type Staged } from './SetDetail';
import { SetWorkbench } from './SetWorkbench';
import { parseSetView, relationId, toggleShow, withSetView, type SetViewState } from './setGraph';

export function ModelSetView() {
  const { setId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getModelSet(setId, signal),
    [client, setId],
  );
  const { state, retry } = useAsync(load);
  const crumbs = [
    { label: 'Models', to: '/models' },
    { label: state.status === 'ready' ? state.data.name : 'Model set' },
  ];
  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Model set not found'
              : 'Could not load this model set'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  if (state.status !== 'ready')
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the model set" />
      </>
    );
  // keyed by the version: a new version (after a save) starts with nothing staged
  return <SetPage key={state.data.id} set={state.data} crumbs={crumbs} />;
}

function SetPage({
  set: initial,
  crumbs,
}: {
  set: ModelSet;
  crumbs: { label: string; to?: string }[];
}) {
  // after a release or a discard the page shows the set the server answered with, without reloading (a reload
  // would start the page again and lose the confirmation)
  const [answered, setAnswered] = useState<ModelSet | null>(null);
  const set = answered ?? initial;
  const client = useApiClient();
  const navigate = useNavigate();
  const location = useLocation();
  const maintainer = useIsMaintainer();

  // arriving after a save: the new version's notice and, for a new lineage, the owner key (shown once)
  const [arrival] = useState(
    () => (location.state as { ownerKey?: string | null; saved?: boolean } | null) ?? null,
  );
  const [keyOpen, setKeyOpen] = useState(Boolean(arrival?.ownerKey));
  useEffect(() => {
    if (arrival) navigate(location.pathname + location.search, { replace: true, state: null });
    // once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // the filter, the checked APIs and the selection are in the URL
  const [params, setParams] = useSearchParams();
  const view = useMemo(() => parseSetView(params, set), [params, set]);
  const latest = useRef(params);
  useEffect(() => {
    latest.current = params;
  }, [params]);
  const update = useCallback(
    (f: (v: SetViewState) => SetViewState) => {
      const next = withSetView(latest.current, f(parseSetView(latest.current, set)));
      latest.current = next;
      setParams(next, { replace: true });
    },
    [set, setParams],
  );
  const [staged, setStaged] = useState<Staged>({});
  const edits = useMemo(() => editsFor(set, staged), [set, staged]);
  const onChoose = useCallback(
    (id: string, index: number | null) =>
      setStaged((s) => {
        if (index === null) return Object.fromEntries(Object.entries(s).filter(([k]) => k !== id));
        return { ...s, [id]: index };
      }),
    [],
  );

  const isLatest = !set.lineage || set.lineage.latestId === set.id;
  const canEdit = set.visibility !== 'discarded' && isLatest;
  const decide = set.undecided
    .map((id) => set.relations.find((r) => r.id === id))
    .filter((r): r is NonNullable<typeof r> => Boolean(r));

  // ---- save the staged design as a new version ----
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<{
    message: string;
    issues: DraftIssue[];
    latest?: boolean;
  } | null>(null);
  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const r = await client.saveSetRelations(set.id, edits);
      if (r.ownerKey) saveOwnerKey(r.ownerKey);
      navigate(`/model-sets/${r.set.id}`, { state: { ownerKey: r.ownerKey, saved: true } });
    } catch (e) {
      if (e instanceof ApiError)
        setSaveError({
          message:
            e.status === 409
              ? 'This is not the latest version of the set, so it cannot be edited. Open the latest version and choose again.'
              : e.status === 401
                ? 'Your session is not valid any more. Sign in again.'
                : e.status === 422
                  ? 'That design was refused, nothing was saved.'
                  : e.message,
          issues: e.issues ?? [],
          latest: e.status === 409,
        });
      else
        setSaveError({ message: e instanceof Error ? e.message : 'Could not save.', issues: [] });
    } finally {
      setSaving(false);
    }
  }
  const saveGoes = maintainer
    ? set.visibility === 'unlisted'
      ? 'a new version of this unlisted set'
      : 'a new unreleased version, for you to review and release'
    : set.visibility === 'official'
      ? 'your own unlisted copy (anyone with its link can see it); the official set stays as it is'
      : 'a new version of this unlisted set (anyone with its link can see it)';

  // ---- release / discard (maintainer) ----
  const [busy, setBusy] = useState<'release' | 'discard' | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  const [released, setReleased] = useState<string[] | null>(null);
  async function run(action: 'release' | 'discard') {
    setBusy(action);
    setReleaseError(null);
    try {
      if (action === 'release') {
        const r = await client.releaseModelSet(set.id);
        setReleased(r.releasedMembers);
        setAnswered(r.set);
      } else setAnswered(await client.discardModelSet(set.id));
      setConfirmDiscard(false);
    } catch (e) {
      setReleaseError(
        e instanceof ApiError && e.status === 401
          ? 'Your session is not valid any more. Sign in again.'
          : e instanceof ApiError && e.status === 409
            ? e.message || 'This set cannot be released now. Reload to see its state.'
            : e instanceof Error
              ? e.message
              : `Could not ${action} the set.`,
      );
    } finally {
      setBusy(null);
    }
  }

  const height = 'clamp(440px, 62vh, 660px)';
  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{set.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <VisibilityChip visibility={set.visibility} />
            <Chip>
              {set.members.length} {set.members.length === 1 ? 'model' : 'models'}
            </Chip>
            <Chip>
              {set.relations.length} {set.relations.length === 1 ? 'relation' : 'relations'}
            </Chip>
            {set.undecided.length ? (
              <Chip tone="warn">{set.undecided.length} to decide</Chip>
            ) : null}
            {set.stale ? <StaleChip inputs={set.staleInputs} /> : null}
          </div>
          <LineageLine snap={set} basePath="/model-sets" />
        </div>
      </div>
      {set.description ? <p className="muted">{set.description}</p> : null}

      <div className="access-banner">
        {arrival?.saved ? (
          <Banner tone="ok" title="Saved as a new version">
            The relations you chose are in this version
            {set.lineage ? ` (v${set.lineage.version} of ${set.lineage.versions})` : ''}.
          </Banner>
        ) : null}
        {arrival?.ownerKey && keyOpen ? (
          <OwnerKeyNotice
            ownerKey={arrival.ownerKey}
            onClose={() => setKeyOpen(false)}
            what="model set"
          />
        ) : null}
        {set.visibility === 'unreleased' ? (
          <Banner tone="warn" title="Unreleased: waiting for your review">
            <p>
              Only signed-in maintainers can see it. Decide every relation, then release it: the set
              and its models become <b>Official</b>.
            </p>
            {decide.length ? (
              <p className="small" role="status">
                <b>Release is blocked:</b> {decide.length}{' '}
                {decide.length === 1 ? 'relation is' : 'relations are'} not decided yet:{' '}
                {decide.map((r, i) => (
                  <Fragment key={r.id}>
                    {i ? ', ' : ''}
                    <button
                      type="button"
                      className="linkbtn"
                      onClick={() => update((v) => ({ ...v, sel: relationId(r.id) }))}
                    >
                      {r.from} → {r.to}
                    </button>
                  </Fragment>
                ))}
                .
              </p>
            ) : null}
            {maintainer ? (
              <div className="row">
                <Button
                  variant="primary"
                  disabled={busy !== null || decide.length > 0}
                  onClick={() => void run('release')}
                >
                  {busy === 'release' ? 'Releasing…' : 'Release'}
                </Button>
                {confirmDiscard ? (
                  <>
                    <span className="small">Discard this set? It cannot be undone.</span>
                    <Button disabled={busy !== null} onClick={() => void run('discard')}>
                      {busy === 'discard' ? 'Discarding…' : 'Yes, discard'}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={busy !== null}
                      onClick={() => setConfirmDiscard(false)}
                    >
                      Keep it
                    </Button>
                  </>
                ) : (
                  <Button disabled={busy !== null} onClick={() => setConfirmDiscard(true)}>
                    Discard
                  </Button>
                )}
              </div>
            ) : (
              <p className="small">
                <Link to="/maintainer">Sign in as a maintainer</Link> to release or discard it.
              </p>
            )}
            {releaseError ? (
              <p role="alert" className="form-error">
                {releaseError}
              </p>
            ) : null}
          </Banner>
        ) : null}
        {released ? (
          <Banner tone="ok" title="Released: the set is Official">
            <p>These models were released with it:</p>
            <ul className="plain">
              {released.map((id) => (
                <li key={id}>
                  <Link className="mono small" to={`/models/${id}`}>
                    {set.members.find((m) => m.modelId === id)?.name ?? id}
                  </Link>
                </li>
              ))}
            </ul>
          </Banner>
        ) : null}
        <LineageHistory snap={set} basePath="/model-sets" what="model set" />
      </div>

      {edits.length ? (
        <Card className="pad set-save" role="region" aria-label="Changes to save">
          <p>
            <b>
              {edits.length} {edits.length === 1 ? 'relation' : 'relations'} changed.
            </b>{' '}
            Saving creates <b>{saveGoes}</b>.
          </p>
          <div className="row">
            <Button variant="primary" disabled={saving} onClick={() => void save()}>
              {saving ? 'Saving…' : 'Save as a new version'}
            </Button>
            <Button variant="ghost" disabled={saving} onClick={() => setStaged({})}>
              Discard changes
            </Button>
          </div>
          {saveError ? (
            <div role="alert" className="form-error">
              {saveError.message}
              {saveError.latest && set.lineage ? (
                <>
                  {' '}
                  <Link to={`/model-sets/${set.lineage.latestId}`}>Open the latest version</Link>
                </>
              ) : null}
              {saveError.issues.length ? (
                <ul className="draft-issues">
                  {saveError.issues.map((i, n) => (
                    <li key={`${i.code}-${n}`}>
                      <Chip tone="bad">{i.code}</Chip> <span className="mono small">{i.field}</span>
                      <div className="muted small">{i.message}</div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </Card>
      ) : null}

      <SetWorkbench
        set={set}
        text={view.f}
        show={view.show}
        selection={view.sel}
        onText={(f) => update((s) => ({ ...s, f }))}
        onToggleApi={(id, on) => update((s) => ({ ...s, show: toggleShow(set, s.show, id, on) }))}
        onSelect={(sel) => update((s) => ({ ...s, sel }))}
        canvasHeight={height}
      >
        <SetDetail
          set={set}
          selection={view.sel}
          staged={staged}
          canEdit={canEdit}
          onChoose={onChoose}
          renderMemberLink={(m) => (
            <Link className="btn primary" to={`/models/${m.modelId}`}>
              Open the field mapping
            </Link>
          )}
          renderDocLink={(apiId, docId) => <Link to={docHref(apiId, docId)}>{docId}</Link>}
        />
        {!canEdit && set.visibility !== 'discarded' ? (
          <p className="small muted">
            This is not the latest version: open the latest to change relations.
          </p>
        ) : null}
      </SetWorkbench>

      <div className="model-cols two-up">
        <ShareCard snap={set} what="model set" />
        <ReviseCard snap={set} what="model set" />
        {set.aliases?.length ? (
          <Card className="pad">
            <h2 className="h2-sm">Same thing, different names</h2>
            <ul className="plain">
              {set.aliases.map((a) => (
                <li key={a.concept}>
                  <b>{a.concept}</b>:{' '}
                  {Object.entries(a.names)
                    .map(
                      ([api, name]) =>
                        `“${name}” in ${set.inputs.find((x) => x.id === api)?.shortName ?? api}`,
                    )
                    .join(', ')}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        <Card className="pad">
          <h2 className="h2-sm">Open questions</h2>
          {set.openQuestions.length === 0 ? (
            <p className="muted">No open questions.</p>
          ) : (
            <ul className="oq">
              {set.openQuestions.map((q) => (
                <li key={q.question}>
                  <div>{richText(q.question)}</div>
                  {q.detail ? <div className="faint small">{q.detail}</div> : null}
                  {q.options?.length ? (
                    <div className="row oq-options" aria-label="Options">
                      {q.options.map((o) => (
                        <Chip key={o}>{o}</Chip>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

// the way a relation reads in a sentence is shared with the editor
export { optionText };
