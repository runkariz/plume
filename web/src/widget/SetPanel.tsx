import { useMemo, useState } from 'react';
import type { ModelSet } from '@/api/types';
import { ApiAvatar, Button, Chip } from '@/components';
import { SetDetail } from '@/pages/sets/SetDetail';
import { SetWorkbench } from '@/pages/sets/SetWorkbench';
import { findMember, relationLabel, SUPPORT_TEXT, toggleShow } from '@/pages/sets/setGraph';
import { OwnerKeyNotice } from './OwnerKeyNotice';
import type { HostConnection } from './protocol';

const VISIBILITY: Record<string, { label: string; tone: 'ok' | 'info' | 'warn' | 'bad' }> = {
  official: { label: 'Official', tone: 'ok' },
  unlisted: { label: 'Unlisted: anyone with the link', tone: 'info' },
  unreleased: { label: 'Unreleased', tone: 'warn' },
  discarded: { label: 'Discarded', tone: 'bad' },
};

/**
 * A model set in the chat: the diagram of its models and relations (read only) and the same as text underneath
 * (models, relations, how each API documents them, what is still to decide). Editing and the field mappings are in
 * Plume itself: "Open in Plume". Everything from the package is a text node.
 */
export function SetPanel({
  set,
  link,
  ownerKey,
  connection,
}: {
  set: ModelSet;
  link: string | null;
  ownerKey: string | null;
  connection: HostConnection | null;
}) {
  const [selection, setSelection] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [show, setShow] = useState<string[] | null>(null);
  const vis = VISIBILITY[set.visibility];
  const canOpen = Boolean(link && connection?.hostCapabilities.openLinks);
  const undecided = useMemo(() => new Set(set.undecided), [set.undecided]);
  return (
    <>
      <div className="widget-head">
        <div>
          <h1 className="widget-title">{set.name}</h1>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            {vis ? <Chip tone={vis.tone}>{vis.label}</Chip> : null}
            {set.lineage && (set.lineage.versions > 1 || set.lineage.basedOn) ? (
              <Chip>
                v{set.lineage.version} of {set.lineage.versions}
              </Chip>
            ) : null}
            <Chip>
              {set.members.length} {set.members.length === 1 ? 'model' : 'models'}
            </Chip>
            <Chip>
              {set.relations.length} {set.relations.length === 1 ? 'relation' : 'relations'}
            </Chip>
            {set.undecided.length ? (
              <Chip tone="warn">{set.undecided.length} to decide</Chip>
            ) : null}
            <span className="widget-apis" aria-label="APIs">
              {set.inputs.map((a) => (
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
          ) : set.sharePath ? (
            <span className="small muted">
              In Plume: <code className="mono">{set.sharePath}</code>
            </span>
          ) : null}
        </div>
      </div>
      {ownerKey ? <OwnerKeyNotice key={ownerKey} ownerKey={ownerKey} what="model set" /> : null}
      {set.description ? <p className="muted">{set.description}</p> : null}
      {set.members.length > 0 ? (
        <SetWorkbench
          set={set}
          text={text}
          show={show}
          selection={selection}
          onText={setText}
          onToggleApi={(id, on) => setShow((s) => toggleShow(set, s, id, on))}
          onSelect={setSelection}
          canvasHeight="400px"
        >
          <SetDetail
            set={set}
            selection={selection}
            staged={{}}
            canEdit={false}
            readOnly
            onChoose={() => undefined}
          />
        </SetWorkbench>
      ) : null}
      <details className="widget-summary widget-text">
        <summary>The models and relations as text</summary>
        <section aria-label="Models">
          <h2 className="h3-sm">Models</h2>
          <ul className="plain">
            {set.members.map((m) => (
              <li key={m.concept}>
                <b>{m.name ?? m.concept}</b>{' '}
                {m.missing ? (
                  <span className="muted small">not available to you</span>
                ) : (
                  <span className="muted small">
                    {m.fieldCount ?? 0} fields
                    {set.inputs
                      .filter((a) => m.coverage?.[a.id])
                      .map(
                        (a) =>
                          ` · ${a.shortName} ${m.coverage?.[a.id]?.mapped}/${m.coverage?.[a.id]?.total}`,
                      )
                      .join('')}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
        <section aria-label="Relations">
          <h2 className="h3-sm">Relations</h2>
          {set.relations.length === 0 ? <p className="muted small">No relations.</p> : null}
          <ul className="plain">
            {set.relations.map((r) => (
              <li key={r.id}>
                <b>
                  {findMember(set, r.from)?.name ?? r.from} → {findMember(set, r.to)?.name ?? r.to}
                </b>{' '}
                <span className="muted small">{relationLabel(r)}</span>
                {undecided.has(r.id) ? <Chip tone="warn">to decide</Chip> : null}
                <div className="small muted">
                  {set.inputs
                    .map((a) => {
                      const how = r.support[a.id];
                      return `${a.shortName} ${how ? SUPPORT_TEXT[how] : 'does not document it'}`;
                    })
                    .join('; ')}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </details>
      <div className="widget-summary">
        {set.openQuestions.length > 0 ? (
          <details className="widget-questions">
            <summary>Open questions ({set.openQuestions.length})</summary>
            <ul>
              {set.openQuestions.map((q) => (
                <li key={q.question}>
                  <div>{q.question}</div>
                  {q.detail ? <div className="faint small">{q.detail}</div> : null}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </>
  );
}
