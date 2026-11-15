import '@xyflow/react/dist/style.css';
import { useEffect, useMemo, useRef, type CSSProperties } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react';
import { ApiAvatar } from '@/components';
import { useTheme } from '@/app/theme';
import { shortBuild } from '@/lib/format';
import type { ModelSnapshot } from '@/api/types';
import {
  buildGraph,
  canonNodeId,
  type CanonNodeData,
  type EdgeData,
  type FieldNodeData,
  type GroupNodeData,
  type ModelNode,
  type Selection,
} from './graph';

function GroupNode({ data }: NodeProps<ModelNode>) {
  const d = data as GroupNodeData;
  return (
    <div className="g-group">
      <div className="g-group-head">
        <ApiAvatar text={d.text} color={d.color} size={26} />
        <b>{d.name}</b>
        <span className="muted small" title={d.build}>
          build {shortBuild(d.build)}
        </span>
      </div>
    </div>
  );
}

function ApiFieldNode({ data }: NodeProps<ModelNode>) {
  const d = data as FieldNodeData;
  return (
    <div className="g-field">
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="mono g-path">{d.path}</div>
      <div className="mono faint small">{d.type}</div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

function CanonicalNode({ data, selected }: NodeProps<ModelNode>) {
  const d = data as CanonNodeData;
  return (
    <div className={`g-canon${selected ? ' sel' : ''}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="g-canon-name mono">{d.field}</div>
      <div className="g-canon-foot">
        <span className="g-avatars">
          {d.support.map((s) => (
            <ApiAvatar
              key={s.apiId}
              text={s.text}
              color={s.color}
              name={s.name}
              kind={
                s.support === 'supported'
                  ? 'direct'
                  : s.support === 'derived'
                    ? 'derived'
                    : 'absent'
              }
              size={24}
            />
          ))}
        </span>
        <span className="mono faint small">{d.type}</span>
        {d.required ? <span className="chip acc">required</span> : null}
      </div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  apiGroup: GroupNode,
  apiField: ApiFieldNode,
  canonical: CanonicalNode,
};

/** Width of the whole graph in graph units (left group, canonical column, right groups). */
const GRAPH_WIDTH = 1500;
/** Below this zoom node text is smaller than ~12 px: the readable view never goes under it. */
export const READABLE_MIN_ZOOM = 0.85;

/** The canvas is a fixed window: a readable view of a big model pans vertically inside it. */
export function graphHeight(readable: boolean): number {
  return readable ? 820 : 760;
}

/** Zoom that fits the graph's width, but never below the readable minimum (then it pans sideways too). */
export function readableZoom(containerWidth: number): number {
  return Math.min(1, Math.max(READABLE_MIN_ZOOM, containerWidth / GRAPH_WIDTH));
}

/** Zooms to the picked field and the API fields it maps to, whenever `focusNonce` changes (not on first render). */
function FocusOnSelection({
  edges,
  selection,
  focusNonce,
}: {
  edges: { source: string; target: string; data?: { field: string } }[];
  selection: Selection | null;
  focusNonce: number;
}) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (focusNonce === 0 || !selection) return;
    const ids = new Set<string>([canonNodeId(selection.field)]);
    for (const e of edges)
      if (e.data?.field === selection.field) {
        ids.add(e.source);
        ids.add(e.target);
      }
    void fitView({
      nodes: [...ids].map((id) => ({ id })),
      padding: 0.25,
      maxZoom: 1.1,
      duration: 400,
    });
    // only a pick from the list moves the view; clicking in the graph must not
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusNonce]);
  return null;
}

function Graph({
  snapshot,
  selection,
  onSelect,
  focusNonce,
  readable,
}: {
  snapshot: ModelSnapshot;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
  focusNonce: number;
  readable: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();
  const base = useMemo(() => buildGraph(snapshot), [snapshot]);

  const edges = useMemo(
    () =>
      base.edges.map((e) => {
        const on =
          selection && e.data?.field === selection.field && e.data.apiId === selection.apiId;
        return {
          ...e,
          selected: Boolean(on),
          style: { ...e.style, strokeWidth: on ? 3.2 : 1.8, opacity: selection && !on ? 0.55 : 1 },
          labelBgStyle: { fill: 'var(--surface)', stroke: 'var(--line)' },
          labelStyle: { ...e.labelStyle, fill: 'var(--ink)' },
        };
      }),
    [base.edges, selection],
  );

  const nodes = useMemo(
    () =>
      base.nodes.map((n) => ({
        ...n,
        selected: n.id === (selection ? canonNodeId(selection.field) : ''),
      })),
    [base.nodes, selection],
  );

  return (
    <div
      className="flow"
      ref={wrap}
      style={{ '--flow-h': `${graphHeight(readable)}px` } as CSSProperties}
      role="group"
      aria-label="Mapping graph (also available as the Mapping list below)"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        colorMode={theme}
        fitView={!readable}
        onInit={(rf) => {
          // a big model opens at a readable zoom, at the top, and pans vertically (no "fit everything")
          if (readable) {
            const z = readableZoom(wrap.current?.clientWidth ?? 1200);
            void rf.setViewport({ x: 12 + 20 * z, y: 12, zoom: z });
          }
        }}
        fitViewOptions={{ padding: 0.06 }}
        minZoom={0.1}
        maxZoom={1.6}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable
        // a long page must scroll over the canvas: zoom with the controls, pinch, or Ctrl/Cmd + wheel
        zoomOnScroll={false}
        panOnScroll={readable}
        preventScrolling={readable}
        proOptions={{ hideAttribution: true }}
        onEdgeClick={(_, edge) => {
          const d = edge.data as EdgeData | undefined;
          if (d) onSelect({ field: d.field, apiId: d.apiId });
        }}
        onNodeClick={(_, node) => {
          const d = node.data;
          if (d.kind === 'canonical') {
            const first = base.edges.find((e) => e.data?.field === d.field);
            if (first?.data) onSelect({ field: d.field, apiId: first.data.apiId });
          } else if (d.kind === 'api-field') {
            const e = base.edges.find((x) => x.source === node.id || x.target === node.id);
            if (e?.data) onSelect({ field: e.data.field, apiId: e.data.apiId });
          }
        }}
      >
        <FocusOnSelection edges={base.edges} selection={selection} focusNonce={focusNonce} />
        <Background gap={22} size={1.5} />
        <MiniMap
          pannable
          zoomable
          position="bottom-left"
          style={{ left: 64, width: 180, height: 110 }}
          ariaLabel="Mini map of the mapping graph"
        />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function MappingGraph(props: {
  snapshot: ModelSnapshot;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
  /** Bump to zoom the view to the current selection. */
  focusNonce?: number;
  /** Open at a readable zoom and pan vertically, instead of fitting everything (for big models). */
  readable?: boolean;
}) {
  return (
    <ReactFlowProvider>
      <Graph {...props} focusNonce={props.focusNonce ?? 0} readable={props.readable ?? false} />
    </ReactFlowProvider>
  );
}
