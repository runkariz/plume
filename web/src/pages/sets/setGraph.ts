import { MarkerType, type Edge, type Node } from '@xyflow/react';
import type { ApiRef, ModelSet, RelationSupport, SetMember, SetRelation } from '@/api/types';

// narrower boxes and gaps: with the control box and the detail panel the canvas is about 700 px wide
export const SET_NODE = { w: 230, h: 120, gapX: 120, gapY: 32 } as const;

/** How an API documents a relation, in words. */
export const SUPPORT_TEXT: Record<RelationSupport, string> = {
  nested: 'as nested objects',
  sub_resource: 'as a sub-resource path',
  id_field: 'as an id field',
  model_ref: 'as a reference to the model',
};

export const memberId = (concept: string) => `m:${concept}`;
export const relationId = (id: string) => `r:${id}`;

/** The member a relation end names: matched case-insensitively, as the server does. */
export function findMember(set: ModelSet, concept: string): SetMember | undefined {
  const c = concept.toLowerCase();
  return set.members.find((m) => m.concept.toLowerCase() === c);
}

export interface MemberNodeData extends Record<string, unknown> {
  member: SetMember;
  inputs: ApiRef[];
}
export type SetNode = Node<MemberNodeData, 'member'>;
export interface RelationEdgeData extends Record<string, unknown> {
  relationId: string;
}

/** "1:n · nested" / "n:1 · reference"; a proposal says so. */
export function relationLabel(r: SetRelation): string {
  const how = r.kind === 'embedded' ? 'nested' : 'reference';
  return `${r.confirmed ? '' : 'proposal · '}${r.cardinality} · ${how}`;
}

/**
 * Lays the models out like a database diagram: columns by how far a model is from a root (a model nothing points
 * at), the relations as arrows from the model that holds to the model that is held. Pure and deterministic.
 * A relation with an end that is not a member cannot be drawn: it is returned in `dropped`.
 */
export function layoutSet(set: ModelSet): {
  nodes: SetNode[];
  edges: Edge<RelationEdgeData>[];
  dropped: string[];
} {
  const drawn: SetRelation[] = [];
  const dropped: string[] = [];
  for (const r of set.relations) {
    if (findMember(set, r.from) && findMember(set, r.to)) drawn.push(r);
    else dropped.push(r.id);
  }
  const key = (c: string) => findMember(set, c)?.concept ?? c;
  const incoming = new Map<string, number>(set.members.map((m) => [m.concept, 0]));
  for (const r of drawn) incoming.set(key(r.to), (incoming.get(key(r.to)) ?? 0) + 1);
  const rank = new Map<string, number>();
  const queue = set.members
    .filter((m) => (incoming.get(m.concept) ?? 0) === 0)
    .map((m) => m.concept);
  // a cycle has no root: start from the first model
  if (queue.length === 0 && set.members[0]) queue.push(set.members[0].concept);
  for (const c of queue) rank.set(c, 0);
  while (queue.length) {
    const c = queue.shift() as string;
    for (const r of drawn)
      if (key(r.from) === c && !rank.has(key(r.to))) {
        rank.set(key(r.to), (rank.get(c) ?? 0) + 1);
        queue.push(key(r.to));
      }
  }
  const rows = new Map<number, number>();
  const nodes: SetNode[] = set.members.map((m) => {
    const col = rank.get(m.concept) ?? 0;
    const row = rows.get(col) ?? 0;
    rows.set(col, row + 1);
    return {
      id: memberId(m.concept),
      type: 'member',
      position: { x: col * (SET_NODE.w + SET_NODE.gapX), y: row * (SET_NODE.h + SET_NODE.gapY) },
      width: SET_NODE.w,
      height: SET_NODE.h,
      draggable: false,
      data: { member: m, inputs: set.inputs },
    };
  });
  const edges: Edge<RelationEdgeData>[] = drawn.map((r) => ({
    id: relationId(r.id),
    source: memberId(key(r.from)),
    target: memberId(key(r.to)),
    type: 'smoothstep',
    label: relationLabel(r),
    data: { relationId: r.id },
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: {
      strokeWidth: r.kind === 'embedded' ? 2.6 : 1.8,
      strokeDasharray: r.confirmed ? undefined : '7 5',
    },
    labelBgPadding: [8, 4],
    labelBgBorderRadius: 10,
    labelStyle: { fontSize: 12, fontWeight: 500 },
    interactionWidth: 24,
    ariaLabel: `${r.from} to ${r.to}, ${relationLabel(r)}`,
  }));
  return { nodes, edges, dropped };
}

export interface SetDimming {
  nodes: Set<string>;
  edges: Set<string>;
}

const has = (hay: string[], text: string) => hay.some((h) => h.toLowerCase().includes(text));

/** Does the name filter match this member / this relation? */
export const memberMatches = (m: SetMember, text: string): boolean =>
  text === '' || has([m.concept, m.name ?? ''], text.toLowerCase());
export const relationMatches = (r: SetRelation, text: string): boolean =>
  text === '' || has([r.id, r.from, r.to, r.kind, r.cardinality], text.toLowerCase());

/** A relation an unchecked-only API documents is greyed out; so is what the name filter leaves out. */
export function relationActive(
  r: SetRelation,
  checked: ReadonlySet<string> | null,
  text: string,
): boolean {
  const apiOk = checked === null || [...checked].some((api) => r.support[api] != null);
  return apiOk && relationMatches(r, text.trim());
}

/**
 * Nothing is hidden, only greyed out (the context stays): a relation is active when one of the checked APIs documents
 * it and it matches the filter; a model when it matches the filter or an active relation touches it, and, with
 * APIs unchecked, when a checked API maps any of its fields.
 */
export function dimmingSet(
  set: ModelSet,
  opts: { checked: ReadonlySet<string> | null; text: string },
): SetDimming {
  const text = opts.text.trim();
  const active = new Set(
    set.relations.filter((r) => relationActive(r, opts.checked, text)).map((r) => r.id),
  );
  const touched = new Set<string>();
  for (const r of set.relations)
    if (active.has(r.id)) {
      touched.add((findMember(set, r.from)?.concept ?? r.from).toLowerCase());
      touched.add((findMember(set, r.to)?.concept ?? r.to).toLowerCase());
    }
  const nodes = new Set<string>();
  for (const m of set.members) {
    const coverageOk =
      opts.checked === null ||
      !m.coverage ||
      [...opts.checked].some((api) => (m.coverage?.[api]?.mapped ?? 0) > 0);
    const textOk = text === '' || memberMatches(m, text) || touched.has(m.concept.toLowerCase());
    if (!coverageOk || !textOk) nodes.add(memberId(m.concept));
  }
  return {
    nodes,
    edges: new Set(set.relations.filter((r) => !active.has(r.id)).map((r) => relationId(r.id))),
  };
}

/** What the page shows and has selected, kept in the URL. */
export interface SetViewState {
  f: string;
  show: string[] | null;
  /** "m:<concept>" or "r:<relation id>" */
  sel: string | null;
}

export function parseSetView(p: URLSearchParams, set: ModelSet): SetViewState {
  const ids = set.inputs.map((a) => a.id);
  const show = (p.get('show') ?? '').split(',').filter((id) => ids.includes(id));
  const sel = p.get('sel');
  const valid =
    sel &&
    ((sel.startsWith('m:') && set.members.some((m) => memberId(m.concept) === sel)) ||
      (sel.startsWith('r:') && set.relations.some((r) => relationId(r.id) === sel)))
      ? sel
      : null;
  return {
    f: (p.get('f') ?? '').trim(),
    show: show.length > 0 && show.length < ids.length ? show : null,
    sel: valid,
  };
}

export function withSetView(base: URLSearchParams, v: SetViewState): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of ['f', 'show', 'sel']) p.delete(k);
  if (v.f) p.set('f', v.f);
  if (v.show) p.set('show', v.show.join(','));
  if (v.sel) p.set('sel', v.sel);
  return p;
}
