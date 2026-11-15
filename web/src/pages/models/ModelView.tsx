import { useCallback, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { useAsync } from '@/api/useAsync';
import { ApiError, type ModelSnapshot } from '@/api/types';
import { Button, Card, Chip, Crumbs, ErrorState, LoadingState } from '@/components';
import { readableOn } from '@/lib/color';
import { richText } from '@/lib/richText';
import { defaultSelection, type Selection } from './graph';
import { MappingGraph } from './MappingGraph';

export function claudePrompt(s: ModelSnapshot): string {
  const apis = s.inputs.map((a) => a.shortName).join(', ');
  return (
    `Use the Plume connector. Call get_snapshot with id "${s.id}": the canonical ${s.name} model for ${apis}. ` +
    `It was generated and is unverified, so check each mapping with search_docs, get_endpoint and find_field ` +
    `before you write any mapping code.`
  );
}

function MappingDetail({ snap, sel }: { snap: ModelSnapshot; sel: Selection }) {
  const field = snap.fields.find((f) => f.name === sel.field);
  const api = snap.inputs.find((a) => a.id === sel.apiId);
  const src = field?.sources[sel.apiId];
  const support = field?.support[sel.apiId];
  if (!field || !api) return null;
  return (
    <>
      <div className="rowhead">
        <h2 className="mono-h">
          {field.name} ← {api.shortName}
        </h2>
        {support === 'derived' ? (
          <Chip tone="warn">derived: {src?.transform?.split(':')[0] ?? 'transform'}</Chip>
        ) : support === 'supported' ? (
          <Chip tone="ok">direct</Chip>
        ) : (
          <Chip>not supported</Chip>
        )}
      </div>
      {!src ? (
        <p className="muted">{api.shortName} has no equivalent field.</p>
      ) : (
        <>
          {src.fetch ? (
            <div className="dl">
              <div className="dl-k">Fetch</div>
              <div className="mono">{src.fetch.endpoint}</div>
            </div>
          ) : null}
          <div className="dl">
            <div className="dl-k">Source</div>
            <div className="mono">{src.paths.map((p) => p.path).join(', ')}</div>
          </div>
          {src.transform && !src.join ? (
            <div className="dl">
              <div className="dl-k">Transform</div>
              <div className="mono">{src.transform}</div>
            </div>
          ) : null}
          {src.join?.length ? (
            <div className="dl">
              <div className="dl-k">Join</div>
              {src.join.map((j) => (
                <div key={j} className="mono">
                  {j}
                </div>
              ))}
            </div>
          ) : null}
          {src.evidence?.map((e) => (
            <blockquote key={e.quote} className="evidence">
              <p>“{e.quote}”</p>
              <cite className="faint small">{e.anchor}</cite>
            </blockquote>
          ))}
        </>
      )}
      {snap.citations.missing.length === 0 ? (
        <p className="cite ok">
          All {snap.citations.checked} cited paths found in the pinned builds
        </p>
      ) : (
        <p className="cite warn">
          {snap.citations.checked - snap.citations.found} of {snap.citations.checked} cited paths
          were not found and were dropped: {snap.citations.missing.join(', ')}
        </p>
      )}
    </>
  );
}

export function ModelView() {
  const { snapshotId = '' } = useParams();
  const client = useApiClient();
  const load = useCallback(
    (signal: AbortSignal) => client.getSnapshot(snapshotId, signal),
    [client, snapshotId],
  );
  const { state, retry } = useAsync(load);
  const [picked, setPicked] = useState<Selection | null>(null);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');

  const snap = state.status === 'ready' ? state.data : null;
  const selection = useMemo(() => picked ?? (snap ? defaultSelection(snap) : null), [picked, snap]);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
    setTimeout(() => setCopied('idle'), 2500);
  }

  const crumbs = [{ label: 'Models', to: '/models' }, { label: snap?.name ?? 'Model' }];

  if (state.status === 'error')
    return (
      <>
        <Crumbs items={crumbs} />
        <ErrorState
          title={
            state.error instanceof ApiError && state.error.status === 404
              ? 'Model not found'
              : 'Could not load this model'
          }
          message={state.error.message}
          onRetry={retry}
        />
      </>
    );
  if (!snap)
    return (
      <>
        <Crumbs items={crumbs} />
        <LoadingState label="Loading the model" />
      </>
    );

  const prompt = claudePrompt(snap);
  const options = snap.fields.flatMap((f) =>
    snap.inputs
      .filter((a) => f.support[a.id] && f.support[a.id] !== 'unsupported')
      .map((a) => ({ value: `${f.name}|${a.id}`, label: `${f.name} ← ${a.shortName}` })),
  );

  return (
    <>
      <Crumbs items={crumbs} />
      <div className="titlerow">
        <div>
          <h1 className="h1-sm">{snap.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <Chip tone="warn">Generated, unverified</Chip>
            <Chip>{snap.inputs.length} APIs</Chip>
            <Chip>{snap.fields.length} fields</Chip>
            <Chip>snapshot {snap.id.replace('_', ' ').replace(/^snap /, 'snap_')}</Chip>
          </div>
        </div>
        <div className="row">
          <Button onClick={() => void copy(prompt)}>Copy for Claude</Button>
          {/* claude.ai/new?q= pre-filling could not be verified, so: copy the prompt, then open a new chat to paste it. */}
          <a
            className="btn primary"
            href="https://claude.ai/new"
            target="_blank"
            rel="noreferrer"
            onClick={() => void copy(prompt)}
          >
            Open in Claude
          </a>
          <span role="status" className="faint small">
            {copied === 'ok'
              ? 'Prompt copied: paste it into Claude'
              : copied === 'fail'
                ? 'Copy failed: select the text instead'
                : ''}
          </span>
        </div>
      </div>
      <div className="legend-line muted small">
        <span>
          <svg width="28" height="6" aria-hidden>
            <line x1="0" y1="3" x2="28" y2="3" stroke="currentColor" strokeWidth="2" />
          </svg>{' '}
          direct
        </span>
        <span>
          <svg width="28" height="6" aria-hidden>
            <line
              x1="0"
              y1="3"
              x2="28"
              y2="3"
              stroke="currentColor"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
          </svg>{' '}
          derived or transformed
        </span>
        <span>no edge = not supported</span>
      </div>
      <MappingGraph snapshot={snap} selection={selection} onSelect={setPicked} />
      <div className="model-cols">
        <Card className="pad">
          <label className="map-pick">
            <span className="sr-only">Mapping</span>
            <select
              className="input"
              value={selection ? `${selection.field}|${selection.apiId}` : ''}
              onChange={(e) => {
                const [field = '', apiId = ''] = e.target.value.split('|');
                setPicked({ field, apiId });
              }}
            >
              {options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {selection ? <MappingDetail snap={snap} sel={selection} /> : null}
        </Card>
        <Card className="pad">
          <h2 className="h2-sm">Open questions</h2>
          {snap.openQuestions.length === 0 ? (
            <p className="muted">No open questions.</p>
          ) : (
            <ul className="oq">
              {snap.openQuestions.map((q) => (
                <li key={q.question}>
                  <div>{richText(q.question)}</div>
                  {q.detail ? <div className="faint small">{q.detail}</div> : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="pad">
          <h2 className="h2-sm">Coverage</h2>
          <ul className="cov">
            {snap.inputs.map((a) => {
              const c = snap.coverage[a.id] ?? { mapped: 0, total: snap.fields.length };
              return (
                <li key={a.id}>
                  <span className="cov-name">
                    <span
                      aria-hidden
                      className="cov-dot"
                      style={{ background: a.logo.color, color: readableOn(a.logo.color) }}
                    >
                      {a.logo.text}
                    </span>
                    {a.shortName}
                  </span>
                  <span
                    className="cov-bar"
                    role="img"
                    aria-label={`${a.shortName}: ${c.mapped} of ${c.total} fields`}
                  >
                    <i
                      style={{
                        width: `${(c.mapped / Math.max(c.total, 1)) * 100}%`,
                        background: a.logo.color,
                      }}
                    />
                  </span>
                  <span className="mono small">
                    {c.mapped} of {c.total}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="faint small">
            Generated by Claude through Plume · prompt {snap.promptVersion}
          </p>
        </Card>
      </div>
    </>
  );
}
