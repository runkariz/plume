import { useEffect, useMemo, useRef, useState } from 'react';
import type { ModelSnapshot } from '@/api/types';
import { FixedThemeProvider, type Theme } from '@/app/theme';
import { ApiAvatar, Banner, Button, Chip, Segmented } from '@/components';
import { countLeaves } from '@/pages/models/fields';
import { ModelWorkbench } from '@/pages/models/ModelWorkbench';
import { defaultSelection, type Selection } from '@/pages/models/graph';
import { toggleApi } from '@/pages/models/modelView';
import { groupWarnings } from '@/pages/models/warnings';
import { extractModel, type Shown } from './model';
import { OwnerKeyNotice } from './OwnerKeyNotice';
import { SetPanel } from './SetPanel';
import type { CallToolResult, HostConnection, HostContext } from './protocol';

/** Above this many fields the embedded view opens on one field, like the page. */
const BIG = 12;

type Phase =
  | { kind: 'connecting' }
  | { kind: 'nohost' }
  | { kind: 'failed'; message: string }
  | Shown
  | { kind: 'waiting' };

const VISIBILITY: Record<string, { label: string; tone: 'ok' | 'info' | 'warn' | 'bad' }> = {
  official: { label: 'Official', tone: 'ok' },
  unlisted: { label: 'Unlisted: anyone with the link', tone: 'info' },
  unreleased: { label: 'Unreleased', tone: 'warn' },
  discarded: { label: 'Discarded', tone: 'bad' },
};

function systemTheme(): Theme {
  return typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

/**
 * The canonical model's mapping view, embedded in a chat (MCP Apps). The host gives the model through the
 * connection; the theme is the host's. Everything shown from the package is a text node.
 */
export function WidgetApp({ connection }: { connection: HostConnection | null }) {
  const [phase, setPhase] = useState<Phase>(
    connection ? { kind: 'connecting' } : { kind: 'nohost' },
  );
  const [ctx, setCtx] = useState<HostContext>({});
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!connection) return;
    let live = true;
    connection.on('ui/notifications/tool-result', (params) => {
      if (live) setPhase(extractModel((params ?? {}) as CallToolResult));
    });
    connection.on('ui/notifications/host-context-changed', (params) => {
      if (live) setCtx({ ...connection.mergeContext(params) });
    });
    connection
      .initialize({ name: 'plume-model-view', version: '1' })
      .then((init) => {
        if (!live) return;
        setCtx(init.hostContext);
        // the result may already have arrived (the host sends it right after `initialized`)
        setPhase((p) => (p.kind === 'connecting' ? { kind: 'waiting' } : p));
      })
      .catch((e: unknown) => {
        if (live)
          setPhase({
            kind: 'failed',
            message: e instanceof Error ? e.message : 'Could not reach the host.',
          });
      });
    return () => {
      live = false;
    };
  }, [connection]);

  // the host decides the theme (and may send its background and font); otherwise the theme's own background is used
  const theme: Theme = ctx.theme ?? systemTheme();
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const bg = ctx.styles?.variables?.['--color-background-primary'];
    if (bg && !/[;{}]/.test(bg)) document.documentElement.style.setProperty('--host-bg', bg);
    else document.documentElement.style.removeProperty('--host-bg');
    // the host's font stack, if it sends one (letters, digits, spaces, commas, quotes and hyphens only)
    const font = ctx.styles?.variables?.['--font-sans'];
    if (font && /^[\w\s,'"-]+$/.test(font))
      document.documentElement.style.setProperty('--host-font-sans', font);
    else document.documentElement.style.removeProperty('--host-font-sans');
  }, [theme, ctx]);

  // the host sizes the frame from what we report
  useEffect(() => {
    if (!connection || !root.current || typeof ResizeObserver === 'undefined') return;
    const el = root.current;
    let last = -1;
    const report = () => {
      const height = Math.ceil(el.getBoundingClientRect().height);
      if (height !== last) {
        last = height;
        connection.sizeChanged({ height });
      }
    };
    const ro = new ResizeObserver(report);
    ro.observe(el);
    report();
    return () => ro.disconnect();
  }, [connection]);

  return (
    <FixedThemeProvider theme={theme}>
      <div ref={root} className="widget">
        <Body phase={phase} connection={connection} />
      </div>
    </FixedThemeProvider>
  );
}

function Body({ phase, connection }: { phase: Phase; connection: HostConnection | null }) {
  switch (phase.kind) {
    case 'connecting':
    case 'waiting':
      return <p className="muted widget-note">Waiting for the model…</p>;
    case 'nohost':
      return (
        <p className="muted widget-note">
          This is the Plume model view. It is shown by a Claude app that supports MCP Apps; open it
          from there.
        </p>
      );
    case 'failed':
      return (
        <Banner tone="bad" title="The model view could not start">
          {phase.message}
        </Banner>
      );
    case 'error':
      return (
        <Banner tone="bad" title="The tool failed">
          {phase.message}
        </Banner>
      );
    case 'pending':
      return (
        <p className="muted widget-note">The model is not ready yet (status: {phase.status}).</p>
      );
    case 'refused':
      return (
        <Banner tone="bad" title="The draft was refused, nothing was stored">
          <ul className="draft-issues">
            {phase.issues.map((i, n) => (
              <li key={`${i.code}-${i.field}-${n}`}>
                <Chip tone="bad">{i.code}</Chip>{' '}
                <span className="mono small">
                  {i.field}
                  {i.api ? ` / ${i.api}` : ''}
                </span>
                <div className="muted small">{i.message}</div>
              </li>
            ))}
          </ul>
        </Banner>
      );
    case 'unrecognised':
      return <p className="muted widget-note">This result has no model to show.</p>;
    case 'set':
      return (
        <SetPanel
          key={phase.set.id}
          set={phase.set}
          link={phase.link}
          ownerKey={phase.ownerKey}
          connection={connection}
        />
      );
    case 'model':
      return (
        <ModelPanel
          key={phase.model.id}
          model={phase.model}
          link={phase.link}
          ownerKey={phase.ownerKey}
          connection={connection}
        />
      );
  }
}

function ModelPanel({
  model,
  link,
  ownerKey,
  connection,
}: {
  model: ModelSnapshot;
  link: string | null;
  ownerKey: string | null;
  connection: HostConnection | null;
}) {
  const big = countLeaves(model) > BIG;
  const [scope, setScope] = useState<'field' | 'all'>(big ? 'field' : 'all');
  const [text, setText] = useState('');
  const [show, setShow] = useState<string[] | null>(null);
  const [picked, setPicked] = useState<Selection | null>(null);
  const selection = useMemo(() => picked ?? defaultSelection(model), [picked, model]);
  const vis = model.visibility ? VISIBILITY[model.visibility] : undefined;
  const lineage = model.lineage;
  const canOpen = Boolean(link && connection?.hostCapabilities.openLinks);

  return (
    <>
      <div className="widget-head">
        <div>
          <h1 className="widget-title">{model.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            {vis ? <Chip tone={vis.tone}>{vis.label}</Chip> : null}
            {lineage && (lineage.versions > 1 || lineage.basedOn) ? (
              <Chip>
                v{lineage.version} of {lineage.versions}
              </Chip>
            ) : null}
            <Chip>{countLeaves(model)} fields</Chip>
            {model.stale ? <Chip tone="warn">Built on older docs</Chip> : null}
            <span className="widget-apis" aria-label="APIs">
              {model.inputs.map((a) => (
                <ApiAvatar
                  key={a.id}
                  text={a.logo.text}
                  color={a.logo.color}
                  name={a.shortName}
                  size={22}
                />
              ))}
            </span>
          </div>
        </div>
        <div className="widget-open">
          {canOpen ? (
            <Button variant="primary" onClick={() => void connection?.openLink(link ?? '')}>
              Open in Plume
            </Button>
          ) : link ? (
            <span className="small muted">
              Open in Plume: <code className="mono">{link}</code>
            </span>
          ) : model.sharePath ? (
            <span className="small muted">
              In Plume: <code className="mono">{model.sharePath}</code>
            </span>
          ) : null}
        </div>
      </div>
      {ownerKey ? <OwnerKeyNotice key={ownerKey} ownerKey={ownerKey} what="model" /> : null}
      {big ? (
        <div className="widget-scope">
          <Segmented
            label="Graph shows"
            variant="pills"
            value={scope}
            onChange={setScope}
            options={[
              { value: 'field', label: 'Selected field' },
              { value: 'all', label: 'Whole model' },
            ]}
          />
        </div>
      ) : null}
      <ModelWorkbench
        snap={model}
        scope={scope}
        readable={big}
        text={text}
        show={show}
        selection={selection}
        onText={setText}
        onToggleApi={(id, on) => setShow((s) => toggleApi(model, s, id, on))}
        onSelect={setPicked}
        canvasHeight={scope === 'field' ? '340px' : '460px'}
      />
      <Summary model={model} />
    </>
  );
}

function Summary({ model }: { model: ModelSnapshot }) {
  const c = model.citations;
  return (
    <div className="widget-summary">
      <ul className="widget-coverage" aria-label="Coverage">
        {model.inputs.map((a) => {
          const cov = model.coverage[a.id] ?? { mapped: 0, total: countLeaves(model) };
          return (
            <li key={a.id}>
              <ApiAvatar text={a.logo.text} color={a.logo.color} size={18} />
              <b>{a.shortName}</b>{' '}
              <span className="mono small">
                {cov.mapped} of {cov.total}
              </span>
            </li>
          );
        })}
      </ul>
      <p className={`small ${c.missing.length === 0 ? 'ok' : 'warn'}`}>
        {c.missing.length === 0
          ? `All ${c.checked} cited paths found in the pinned builds`
          : `${c.checked - c.found} of ${c.checked} cited paths were not found and were dropped`}
      </p>
      {groupWarnings(model.warnings).map((g) => (
        <p key={g.code} className="small warn">
          {g.summary}: <span className="mono">{g.items.map((w) => w.field ?? '?').join(', ')}</span>
        </p>
      ))}
      {model.openQuestions.length > 0 ? (
        <details className="widget-questions">
          <summary>Open questions ({model.openQuestions.length})</summary>
          <ul>
            {model.openQuestions.map((q) => (
              <li key={q.question}>
                {/* plain text: the question may carry **bold** marks, which are shown as they are here */}
                <div>{q.question}</div>
                {q.detail ? <div className="faint small">{q.detail}</div> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
