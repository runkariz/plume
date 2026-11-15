import type { Edge, Node } from '@xyflow/react';
import type { ModelSnapshot } from '@/api/types';

export const NODE = {
  groupW: 400,
  fieldW: 360,
  fieldH: 62,
  gap: 28,
  canonW: 320,
  canonH: 96,
  canonGap: 24,
  groupPadTop: 56,
  groupPadBottom: 24,
  groupGap: 36,
  centerX: 560,
  rightX: 1040,
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
  support: { apiId: string; text: string; color: string; name: string; support: string }[];
}
export interface GroupNodeData extends Record<string, unknown> {
  kind: 'group';
  apiId: string;
  name: string;
  build: string;
  text: string;
  color: string;
}
export interface EdgeData extends Record<string, unknown> {
  field: string;
  apiId: string;
  derived: boolean;
}

export type ModelNode = Node<FieldNodeData | CanonNodeData | GroupNodeData>;
export type ModelEdge = Edge<EdgeData>;

const fieldNodeId = (apiId: string, path: string) => `api:${apiId}:${path}`;
export const canonNodeId = (field: string) => `canon:${field}`;
const groupNodeId = (apiId: string) => `group:${apiId}`;

/**
 * Lays the snapshot out like mockup 11: the first API on the left, the canonical fields in the middle,
 * the other APIs stacked on the right. Pure and deterministic, so it is unit tested without React Flow.
 */
export function buildGraph(snap: ModelSnapshot): { nodes: ModelNode[]; edges: ModelEdge[] } {
  const nodes: ModelNode[] = [];
  const edges: ModelEdge[] = [];
  const canonY = (i: number) => 24 + i * (NODE.canonH + NODE.canonGap);

  // canonical column
  snap.fields.forEach((f, i) => {
    nodes.push({
      id: canonNodeId(f.name),
      type: 'canonical',
      position: { x: NODE.centerX, y: canonY(i) + NODE.groupPadTop - 24 },
      width: NODE.canonW,
      height: NODE.canonH,
      draggable: false,
      data: {
        kind: 'canonical',
        field: f.name,
        type: f.type,
        required: f.required,
        support: snap.inputs.map((a) => ({
          apiId: a.id,
          text: a.logo.text,
          color: a.logo.color,
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
    const x = left ? 0 : NODE.rightX;
    // unique source paths in order of first use, each aligned to its first canonical row when on the left
    const used: { path: string; type: string; row: number }[] = [];
    snap.fields.forEach((f, row) => {
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
      width: NODE.groupW,
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
      },
    });
    used.forEach((u, i) => {
      nodes.push({
        id: fieldNodeId(api.id, u.path),
        type: 'apiField',
        position: { x, y: positions[i] ?? 0 },
        width: NODE.fieldW,
        height: NODE.fieldH,
        draggable: false,
        data: { kind: 'api-field', apiId: api.id, path: u.path, type: u.type },
      });
    });
    if (!left) rightCursor = top + height + NODE.groupGap;
  });

  // edges: one per (canonical field, api, source path)
  snap.fields.forEach((f) => {
    snap.inputs.forEach((api, apiIndex) => {
      const support = f.support[api.id];
      const src = f.sources[api.id];
      if (!src || support === 'unsupported' || support === undefined) return;
      const derived = support === 'derived';
      for (const p of src.paths) {
        const left = apiIndex === 0;
        const apiNode = fieldNodeId(api.id, p.path);
        edges.push({
          id: `${f.name}__${api.id}__${p.path}`,
          source: left ? apiNode : canonNodeId(f.name),
          target: left ? canonNodeId(f.name) : apiNode,
          type: 'default',
          label: derived ? (src.transform ?? (src.join?.length ? 'join' : undefined)) : undefined,
          data: { field: f.name, apiId: api.id, derived },
          style: {
            stroke: api.logo.color,
            strokeWidth: 1.8,
            strokeDasharray: derived ? '7 5' : undefined,
          },
          labelBgPadding: [8, 4],
          labelBgBorderRadius: 10,
          labelStyle: { fontSize: 12, fontWeight: 500 },
          interactionWidth: 24,
          ariaLabel: `${f.name} ${left ? 'from' : 'to'} ${api.shortName}${derived ? ' (derived)' : ''}`,
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
  for (const f of snap.fields) {
    for (const api of snap.inputs) {
      const s = f.support[api.id];
      if (s === 'derived') return { field: f.name, apiId: api.id };
      if (s === 'supported' && !first) first = { field: f.name, apiId: api.id };
    }
  }
  return first;
}
