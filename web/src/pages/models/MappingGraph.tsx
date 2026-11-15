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
  getNodesBounds,
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
  dimming,
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
        <ApiAvatar text={d.text} color={d.color} url={d.url} size={26} />
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
              url={s.url}
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

const NO_DIM = { checked: null, text: '' } as const;

/** Width of the whole graph in graph units (left group, canonical column, right groups). */
const GRAPH_WIDTH = 1260;
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

/** The control box covers the left of the canvas: fit the view to what is left of it. */
export function fitPadding(inset: number, ratio = 0.06) {
  return {
    top: `${Math.round(ratio * 100)}%`,
    bottom: `${Math.round(ratio * 100)}%`,
    right: `${Math.round(ratio * 100)}%`,
    left: `${inset + 16}px`,
  } as const;
}

/** Fits (or, for a big model, repositions) the view again when the control box opens or closes. */
function Refit({
  inset,
  readable,
  fit,
  containerWidth,
}: {
  inset: number;
  readable: boolean;
  fit: 'all' | 'field';
  containerWidth: () => number;
}) {
  const rf = useReactFlow();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false; // the first fit is done by the canvas itself
      return;
    }
    if (readable) {
      const z = readableZoom(containerWidth());
      void rf.setViewport({ x: inset + 12 + 20 * z, y: 12, zoom: z }, { duration: 250 });
    } else {
      void rf.fitView({
        padding: fitPadding(inset, fit === 'field' ? 0.1 : 0.06),
        maxZoom: fit === 'field' ? 1.2 : 1,
        duration: 250,
      });
    }
    // only the box opening or closing moves the view
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inset]);
  return null;
}

/**
 * When the checked APIs change, brings the view to the nodes that are still active (not greyed out), so that
 * "WooCommerce only" shows WooCommerce instead of leaving it off screen. Not on first render, not for the name
 * filter (the view must not jump on every key).
 */
function FocusOnApis({
  nodes,
  dimmedNodes,
  checkedKey,
  inset,
  readable,
  containerWidth,
}: {
  nodes: { id: string }[];
  dimmedNodes: ReadonlySet<string>;
  checkedKey: string;
  inset: number;
  readable: boolean;
  containerWidth: () => number;
}) {
  const rf = useReactFlow();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const active = nodes.filter((n) => !dimmedNodes.has(n.id));
    if (active.length === 0 || checkedKey === '') {
      // everything is checked again: back to the overview
      void rf.fitView({ padding: fitPadding(inset), duration: 300 });
      return;
    }
    if (readable) {
      // a big model keeps its readable zoom and shows the top of the active nodes
      const b = getNodesBounds(rf.getNodes().filter((n) => !dimmedNodes.has(n.id)));
      const z = readableZoom(containerWidth() - inset);
      void rf.setViewport({ x: inset + 12 - b.x * z, y: 12 - b.y * z, zoom: z }, { duration: 300 });
    } else {
      void rf.fitView({
        nodes: active.map((n) => ({ id: n.id })),
        padding: fitPadding(inset),
        maxZoom: 1,
        duration: 300,
      });
    }
    // only a change of the checked APIs moves the view
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkedKey]);
  return null;
}

/** Zooms to the picked field and the API fields it maps to, whenever `focusNonce` changes (not on first render). */
function FocusOnSelection({
  edges,
  selection,
  focusNonce,
  inset,
}: {
  edges: { source: string; target: string; data?: { field: string } }[];
  selection: Selection | null;
  focusNonce: number;
  inset: number;
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
      padding: fitPadding(inset, 0.1),
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
  dim,
  inset,
  fit,
  height,
}: {
  snapshot: ModelSnapshot;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
  focusNonce: number;
  readable: boolean;
  dim: { checked: ReadonlySet<string> | null; text: string };
  inset: number;
  fit: 'all' | 'field';
  height: string | number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();
  const base = useMemo(() => buildGraph(snapshot, { compact: fit === 'field' }), [snapshot, fit]);

  const dimmed = useMemo(() => dimming(base, dim), [base, dim]);

  const edges = useMemo(
    () =>
      base.edges.map((e) => {
        const on =
          selection && e.data?.field === selection.field && e.data.apiId === selection.apiId;
        const off = dimmed.edges.has(e.id);
        return {
          ...e,
          selected: Boolean(on),
          className: off ? 'dim' : undefined,
          style: {
            ...e.style,
            strokeWidth: on ? 3.2 : 1.8,
            // greyed out (not hidden): the selected mapping stays visible even when its API is unchecked
            opacity: off ? (on ? 0.5 : 0.14) : selection && !on ? 0.55 : 1,
          },
          labelBgStyle: { fill: 'var(--surface)', stroke: 'var(--line)' },
          labelStyle: { ...e.labelStyle, fill: 'var(--ink)' },
        };
      }),
    [base.edges, selection, dimmed],
  );

  const nodes = useMemo(
    () =>
      base.nodes.map((n) => ({
        ...n,
        className: dimmed.nodes.has(n.id) ? 'dim' : undefined,
        selected: n.id === (selection ? canonNodeId(selection.field) : ''),
      })),
    [base.nodes, selection, dimmed],
  );

  return (
    <div
      className="flow"
      ref={wrap}
      style={{ '--flow-h': typeof height === 'number' ? `${height}px` : height } as CSSProperties}
      role="group"
      aria-label="Mapping graph (the same mappings are in the control box, as a list)"
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
            void rf.setViewport({ x: inset + 12 + 20 * z, y: 12, zoom: z });
          }
        }}
        fitViewOptions={{
          padding: fitPadding(inset, fit === 'field' ? 0.1 : 0.06),
          maxZoom: fit === 'field' ? 1.2 : 1,
        }}
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
        <FocusOnSelection
          edges={base.edges}
          selection={selection}
          focusNonce={focusNonce}
          inset={inset}
        />
        <FocusOnApis
          nodes={base.nodes}
          dimmedNodes={dimmed.nodes}
          checkedKey={dim.checked ? [...dim.checked].sort().join(',') : ''}
          inset={inset}
          readable={readable}
          containerWidth={() => wrap.current?.clientWidth ?? 1200}
        />
        <Refit
          inset={inset}
          readable={readable}
          fit={fit}
          containerWidth={() => wrap.current?.clientWidth ?? 1200}
        />
        <Background gap={22} size={1.5} />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          style={{ right: 64, width: 180, height: 110 }}
          ariaLabel="Mini map of the mapping graph"
        />
        <Controls showInteractive={false} position="bottom-right" />
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
  /** Greys out (never hides) what is filtered away or belongs to an unchecked API. */
  dim?: { checked: ReadonlySet<string> | null; text: string };
  /** Width in px of the control box over the left of the canvas: the view fits to what is left of it. */
  inset?: number;
  /** "field": a single field is shown, so zoom in on it instead of leaving an empty canvas. */
  fit?: 'all' | 'field';
  height?: string | number;
}) {
  const readable = props.readable ?? false;
  return (
    <ReactFlowProvider>
      <Graph
        {...props}
        focusNonce={props.focusNonce ?? 0}
        readable={readable}
        dim={props.dim ?? NO_DIM}
        inset={props.inset ?? 0}
        fit={props.fit ?? 'all'}
        height={props.height ?? graphHeight(readable)}
      />
    </ReactFlowProvider>
  );
}
