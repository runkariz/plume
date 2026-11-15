import { useId } from 'react';
import { Link } from 'react-router-dom';
import type { ModelSet, RelationEdit, RelationOption, SetMember, SetRelation } from '@/api/types';
import { ApiAvatar, Chip } from '@/components';
import { docHref } from '@/lib/docHref';
import { findMember, SUPPORT_TEXT } from './setGraph';

/** The design choices staged on this page: a relation id and the index of the chosen option. */
export type Staged = Record<string, number>;

/** What choosing an option changes: it is a change unless it is the decided design the relation already has. */
export function isChange(r: SetRelation, o: RelationOption): boolean {
  return !(r.confirmed && o.current);
}

/** The request body for the staged choices: the design fields of the chosen option, and confirmed. */
export function editsFor(set: ModelSet, staged: Staged): RelationEdit[] {
  return Object.entries(staged).flatMap(([id, index]) => {
    const r = set.relations.find((x) => x.id === id);
    const o = r?.editableOptions?.[index];
    if (!r || !o || !o.editable) return [];
    return [
      {
        id,
        kind: o.kind,
        cardinality: o.cardinality,
        from: o.from,
        to: o.to,
        ...(o.embed ? { embed: o.embed } : {}),
        ...(o.ref ? { ref: o.ref } : {}),
        confirmed: true,
      },
    ];
  });
}

export function optionText(o: RelationOption): string {
  return o.kind === 'embedded'
    ? `${o.from} embeds ${o.to}${o.embed ? `, in "${o.embed.field}"` : ''}`
    : `${o.from} refers to ${o.to}${o.ref ? `, by "${o.ref.field}" (the ${o.to} ${o.ref.key})` : ''}`;
}

function MemberDetail({ set, member }: { set: ModelSet; member: SetMember }) {
  const alias = set.aliases?.find((a) => a.concept.toLowerCase() === member.concept.toLowerCase());
  const touching = set.relations.filter(
    (r) =>
      findMember(set, r.from)?.concept === member.concept ||
      findMember(set, r.to)?.concept === member.concept,
  );
  return (
    <>
      <div className="rowhead">
        <h2 className="mono-h">{member.name ?? member.concept}</h2>
        {member.missing ? (
          <Chip tone="warn">Not available</Chip>
        ) : (
          <Chip>{member.fieldCount ?? 0} fields</Chip>
        )}
      </div>
      {member.missing ? (
        <p className="muted">
          This model is not available to you (it is not released, or you cannot see it).
        </p>
      ) : (
        <>
          <ul className="wb-detail-cov" aria-label="Coverage">
            {set.inputs.map((a) => {
              const c = member.coverage?.[a.id];
              return c ? (
                <li key={a.id}>
                  <ApiAvatar text={a.logo.text} color={a.logo.color} size={18} />{' '}
                  <b>{a.shortName}</b>{' '}
                  <span className="mono small">
                    {c.mapped} of {c.total}
                  </span>
                </li>
              ) : null;
            })}
          </ul>
          {alias ? (
            <p className="muted small">
              Called{' '}
              {Object.entries(alias.names)
                .map(
                  ([api, name]) =>
                    `“${name}” in ${set.inputs.find((a) => a.id === api)?.shortName ?? api}`,
                )
                .join(', ')}
              .
            </p>
          ) : null}
          <Link className="btn primary" to={`/models/${member.modelId}`}>
            Open the field mapping
          </Link>
        </>
      )}
      {touching.length ? (
        <p className="faint small">
          In {touching.length} {touching.length === 1 ? 'relation' : 'relations'}:{' '}
          {touching.map((r) => `${r.from} → ${r.to}`).join(', ')}
        </p>
      ) : null}
    </>
  );
}

function RelationDetail({
  set,
  relation: r,
  staged,
  canEdit,
  onChoose,
}: {
  set: ModelSet;
  relation: SetRelation;
  staged: Staged;
  canEdit: boolean;
  onChoose: (relationId: string, index: number | null) => void;
}) {
  const name = useId();
  const options = r.editableOptions ?? [];
  const stagedIndex = staged[r.id];
  return (
    <>
      <div className="rowhead">
        <h2 className="mono-h">
          {r.from} → {r.to}
        </h2>
        {r.confirmed ? (
          <Chip tone="ok">Decided</Chip>
        ) : (
          <Chip tone="warn">Proposal: to decide</Chip>
        )}
      </div>
      <p className="muted small">
        {r.kind === 'embedded'
          ? `${r.from} contains ${r.to}${r.embed ? ` in its field “${r.embed.field}”` : ''}`
          : `${r.from} refers to ${r.to}${r.ref ? ` by “${r.ref.field}”` : ''}`}{' '}
        <Chip>{r.cardinality}</Chip>
      </p>

      {options.length ? (
        <fieldset className="rel-design">
          <legend>Design of this relation</legend>
          {options.map((o, i) => {
            const checked =
              stagedIndex === i || (stagedIndex === undefined && r.confirmed && o.current);
            const disabled = !canEdit || !o.editable;
            return (
              <label
                key={i}
                className={`rel-option${disabled ? ' off' : ''}${checked ? ' on' : ''}`}
              >
                <input
                  type="radio"
                  name={name}
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onChoose(r.id, isChange(r, o) ? i : null)}
                />
                <span>
                  <span className="rel-option-text">{optionText(o)}</span>{' '}
                  <Chip>{o.cardinality}</Chip>
                  {o.current ? <Chip tone="info">current</Chip> : null}
                  {!o.editable ? (
                    <span className="small muted rel-missing">
                      Not possible yet: {o.missing.join('; ')}. Revise the set with Claude to add
                      it.
                    </span>
                  ) : null}
                </span>
              </label>
            );
          })}
          {stagedIndex !== undefined ? (
            <p className="small">
              <b>Staged:</b> {optionText(options[stagedIndex] as RelationOption)}.{' '}
              <button type="button" className="linkbtn" onClick={() => onChoose(r.id, null)}>
                Undo
              </button>
            </p>
          ) : !r.confirmed ? (
            <p className="small muted">Pick a design to confirm this relation.</p>
          ) : null}
        </fieldset>
      ) : null}
      <h3 className="h3-sm">How each API documents it</h3>
      <ul className="rel-sources" aria-label="Sources">
        {set.inputs.map((a) => {
          const how = r.support[a.id];
          const src = r.sources[a.id];
          const fetch = typeof src?.fetch === 'string' ? src.fetch : src?.fetch?.endpoint;
          return (
            <li key={a.id}>
              <ApiAvatar text={a.logo.text} color={a.logo.color} size={18} /> <b>{a.shortName}</b>{' '}
              <span className="muted small">
                {how ? SUPPORT_TEXT[how] : 'does not document it'}
              </span>
              {src && how ? (
                <>
                  {src.paths.length ? (
                    <div className="mono small">{src.paths.join(', ')}</div>
                  ) : null}
                  {fetch ? <div className="mono small faint">{fetch}</div> : null}
                  {src.evidence?.map((e, i) => (
                    <blockquote key={`${e.docId ?? ''}-${i}`} className="evidence">
                      <p>“{e.quote}”</p>
                      {e.docId ? (
                        <cite className="faint small">
                          <Link to={docHref(a.id, e.docId)}>{e.docId}</Link>
                        </cite>
                      ) : null}
                    </blockquote>
                  ))}
                </>
              ) : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** The model or the relation picked in the diagram, with the editor for a relation. */
export function SetDetail({
  set,
  selection,
  staged,
  canEdit,
  onChoose,
}: {
  set: ModelSet;
  selection: string | null;
  staged: Staged;
  canEdit: boolean;
  onChoose: (relationId: string, index: number | null) => void;
}) {
  const relation = selection?.startsWith('r:')
    ? set.relations.find((r) => `r:${r.id}` === selection)
    : undefined;
  const member = selection?.startsWith('m:')
    ? set.members.find((m) => `m:${m.concept}` === selection)
    : undefined;
  if (relation)
    return (
      <RelationDetail
        set={set}
        relation={relation}
        staged={staged}
        canEdit={canEdit}
        onChoose={onChoose}
      />
    );
  if (member) return <MemberDetail set={set} member={member} />;
  return <p className="muted">Pick a model or a relation in the diagram or in the list.</p>;
}
