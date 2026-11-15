import type { Edge, Node } from '@xyflow/react';
import type { ModelSnapshot } from '@/api/types';
import { fieldPath, mappedFields } from './fields';

export const NODE = {
  // narrower than the first version (1500 units): with the control box and the detail panel the canvas is about
  // 900 px wide, and the graph has to stay readable there
  groupW: 360,
  fieldW: 320,
  fieldH: 62,
  gap: 28,
  canonW: 280,
  canonH: 96,
  canonGap: 24,
  groupPadTop: 56,
  groupPadBottom: 24,
  groupGap: 36,
  centerX: 470,
  rightX: 900,
} as const;

export interface FieldNodeData extends Record<string, unknown> {
  kind: 'api-field';
  apiId: string;
  path: string;
  type: string;
}
export interface CanonNodeData extends Record<string, unknown> {
  kind: 'canonical';
  field: string;
  type: string;
  required: boolean;
  support: {
    apiId: string;
    text: string;
    color: string;
    url?: string | null;
    name: string;
    support: string;
  }[];
}
export interface GroupNodeData extends Record<string, unknown> {
  kind: 'group';
  apiId: string;
  name: string;
  build: string;
  text: string;
  color: string;
  url?: string | null;
}
export interface EdgeData extends Record<string, unknown> {
  field: string;
  apiId: string;
  /** The source path this edge goes to (what the name filter looks at besides the field). */
  path: string;
  derived: boolean;
}

export type ModelNode = Node<FieldNodeData | CanonNodeData | GroupNodeData>;
export type ModelEdge = Edge<EdgeData>;

/** Edge labels stay short: transforms in real models are whole sentences (the table and the detail card show them in full). */
export const MAX_EDGE_LABEL = 26;
export function edgeLabel(transform?: string | null, join?: string[]): string | undefined {
  const text = transform?.trim() || (join?.length ? 'join' : undefined);
  if (!text) return undefined;
  return text.length > MAX_EDGE_LABEL ? `${text.slice(0, MAX_EDGE_LABEL - 1).trimEnd()}…` : text;
}

const fieldNodeId = (apiId: string, path: string) => `api:${apiId}:${path}`;
export const canonNodeId = (field: string) => `canon:${field}`;
const groupNodeId = (apiId: string) => `group:${apiId}`;

/**
 * Lays the snapshot out like mockup 11: the first API on the left, the canonical fields in the middle,
 * the other APIs stacked on the right. Pure and deterministic, so it is unit tested without React Flow.
 */
export function buildGraph(
  snap: ModelSnapshot,
  opts: { compact?: boolean } = {},
): { nodes: ModelNode[]; edges: ModelEdge[] } {
  // compact: one field and the APIs behind it. The columns come closer so the field can be drawn larger, and the
  // edge labels are left out (the detail panel says the transform in full).
  const L = opts.compact
    ? { ...NODE, fieldW: 260, canonW: 220, groupW: 300, centerX: 340, rightX: 640 }
    : NODE;
  const nodes: ModelNode[] = [];
  const edges: ModelEdge[] = [];
  const canonY = (i: number) => 24 + i * (NODE.canonH + NODE.canonGap);

  // canonical column
  const mapped = mappedFields(snap);
  mapped.forEach(({ field: f }, i) => {
    nodes.push({
      id: canonNodeId(fieldPath(f)),
      type: 'canonical',
      position: { x: L.centerX, y: canonY(i) + NODE.groupPadTop - 24 },
      width: L.canonW,
      height: NODE.canonH,
      draggable: false,
      data: {
        kind: 'canonical',
        field: fieldPath(f),
        type: f.type,
        required: f.required,
        support: snap.inputs.map((a) => ({
          apiId: a.id,
          text: a.logo.text,
          color: a.logo.color,
          url: a.logo.url,
          name: a.shortName,
          support: f.support[a.id] ?? 'unsupported',
        })),
      },
    });
  });

  // API groups: first on the left, the rest stacked on the right
  let rightCursor = 0;
  snap.inputs.forEach((api, apiIndex) => {
    const left = apiIndex === 0;
    const x = left ? 0 : L.rightX;
    // unique source paths in order of first use, each aligned to its first canonical row when on the left
    const used: { path: string; type: string; row: number }[] = [];
    mapped.forEach(({ field: f }, row) => {
      for (const p of f.sources[api.id]?.paths ?? []) {
        if (!used.some((u) => u.path === p.path)) used.push({ path: p.path, type: p.type, row });
      }
    });
    const step = NODE.fieldH + NODE.gap;
    const top = left ? 0 : rightCursor;
    const positions: number[] = [];
    used.forEach((u, i) => {
      const wanted = left
        ? canonY(u.row) + NODE.groupPadTop - 24 + (NODE.canonH - NODE.fieldH) / 2
        : top + NODE.groupPadTop + i * step;
      const prev = positions[i - 1];
      positions.push(
        prev === undefined
          ? Math.max(wanted, top + NODE.groupPadTop)
          : Math.max(wanted, prev + step),
      );
    });
    const last = positions[positions.length - 1];
    const bottom = last === undefined ? top + NODE.groupPadTop : last + NODE.fieldH;
    const height = bottom - top + NODE.groupPadBottom;
    nodes.push({
      id: groupNodeId(api.id),
      type: 'apiGroup',
      position: { x: x - 20, y: top },
      width: L.groupW,
      height,
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
      data: {
        kind: 'group',
        apiId: api.id,
        name: api.shortName,
        build: api.build,
        text: api.logo.text,
        color: api.logo.color,
        url: api.logo.url,
      },
    });
    used.forEach((u, i) => {
      nodes.push({
        id: fieldNodeId(api.id, u.path),
        type: 'apiField',
        position: { x, y: positions[i] ?? 0 },
        width: L.fieldW,
        height: NODE.fieldH,
        draggable: false,
        data: { kind: 'api-field', apiId: api.id, path: u.path, type: u.type },
      });
    });
    if (!left) rightCursor = top + height + NODE.groupGap;
  });

  // edges: one per (canonical field, api, source path)
  mapped.forEach(({ field: f }) => {
    snap.inputs.forEach((api, apiIndex) => {
      const support = f.support[api.id];
      const src = f.sources[api.id];
      if (!src || support === 'unsupported' || support === undefined) return;
      const derived = support === 'derived';
      for (const p of src.paths) {
        const left = apiIndex === 0;
        const apiNode = fieldNodeId(api.id, p.path);
        edges.push({
          id: `${fieldPath(f)}__${api.id}__${p.path}`,
          source: left ? apiNode : canonNodeId(fieldPath(f)),
          target: left ? canonNodeId(fieldPath(f)) : apiNode,
          type: 'default',
          label: derived && !opts.compact ? edgeLabel(src.transform, src.join) : undefined,
          data: { field: fieldPath(f), apiId: api.id, path: p.path, derived },
          style: {
            stroke: api.logo.color,
            strokeWidth: 1.8,
            strokeDasharray: derived ? '7 5' : undefined,
          },
          labelBgPadding: [8, 4],
          labelBgBorderRadius: 10,
          labelStyle: { fontSize: 12, fontWeight: 500 },
          interactionWidth: 24,
          ariaLabel: `${fieldPath(f)} ${left ? 'from' : 'to'} ${api.shortName}${derived ? ' (derived)' : ''}`,
        });
      }
    });
  });

  return { nodes, edges };
}

export interface Selection {
  field: string;
  apiId: string;
}

/** The mapping the detail panel opens with: the first derived one, else the first one. */
export function defaultSelection(snap: ModelSnapshot): Selection | null {
  let first: Selection | null = null;
  for (const { field: f } of mappedFields(snap)) {
    for (const api of snap.inputs) {
      const s = f.support[api.id];
      if (s === 'derived') return { field: fieldPath(f), apiId: api.id };
      if (s === 'supported' && !first) first = { field: fieldPath(f), apiId: api.id };
    }
  }
  return first;
}

/** What the graph greys out: nodes and edges that are filtered away or belong to an unchecked API. */
export interface Dimming {
  nodes: Set<string>;
  edges: Set<string>;
}

/**
 * Nothing is hidden, only greyed out, so the context stays: an edge is active when its API is checked and, with a
 * name filter, its canonical field or its source path contains the text. A node is active when an active edge
 * touches it (a canonical field also when its own name matches); a group follows its API's checkbox.
 * `checked` null means every API is checked.
 */
export function dimming(
  g: { nodes: ModelNode[]; edges: ModelEdge[] },
  opts: { checked: ReadonlySet<string> | null; text: string },
): Dimming {
  const text = opts.text.trim().toLowerCase();
  const on = (apiId: string) => opts.checked === null || opts.checked.has(apiId);
  const hit = (...values: string[]) =>
    text === '' || values.some((v) => v.toLowerCase().includes(text));
  const activeEdges = new Set<string>();
  const touched = new Set<string>();
  for (const e of g.edges) {
    const d = e.data;
    if (d && on(d.apiId) && hit(d.field, d.path)) {
      activeEdges.add(e.id);
      touched.add(e.source);
      touched.add(e.target);
    }
  }
  const nodes = new Set<string>();
  for (const n of g.nodes) {
    const d = n.data;
    if (d.kind === 'group') {
      if (!on(d.apiId)) nodes.add(n.id);
    } else if (d.kind === 'canonical') {
      const edgeless = !g.edges.some((e) => e.source === n.id || e.target === n.id);
      const active =
        touched.has(n.id) || (text !== '' && hit(d.field)) || (edgeless && text === '');
      if (!active) nodes.add(n.id);
    } else if (!touched.has(n.id)) {
      nodes.add(n.id);
    }
  }
  const edges = new Set(g.edges.filter((e) => !activeEdges.has(e.id)).map((e) => e.id));
  return { nodes, edges };
}

/** One row of the mapping list: a canonical field and one API that fills it. */
export interface MappingRow {
  /** The canonical path. */
  field: string;
  /** How deep the field sits (0 = top level): the list indents by it. */
  depth: number;
  apiId: string;
  apiName: string;
  kind: 'supported' | 'derived';
  paths: string[];
}

export function mappingRows(snap: ModelSnapshot): MappingRow[] {
  return mappedFields(snap).flatMap(({ field: f, depth }) =>
    snap.inputs.flatMap((a) => {
      const support = f.support?.[a.id];
      if (support !== 'supported' && support !== 'derived') return [];
      return [
        {
          field: fieldPath(f),
          depth,
          apiId: a.id,
          apiName: a.shortName,
          kind: support,
          paths: (f.sources?.[a.id]?.paths ?? []).map((p) => p.path),
        },
      ];
    }),
  );
}

/** A row matches the name filter by its canonical field or any of its source paths. */
export function rowMatches(row: MappingRow, text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t === '' ||
    row.field.toLowerCase().includes(t) ||
    row.paths.some((p) => p.toLowerCase().includes(t))
  );
}
