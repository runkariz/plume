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
import type { ModelSet } from '@/api/types';
import { useTheme } from '@/app/theme';
import { ApiAvatar } from '@/components';
import { fitPadding } from '@/pages/models/MappingGraph';
import {
  dimmingSet,
  layoutSet,
  memberId,
  relationId,
  type RelationEdgeData,
  type SetNode,
} from './setGraph';

const VIS: Record<string, string> = {
  unreleased: 'Unreleased',
  unlisted: 'Unlisted',
  discarded: 'Discarded',
};

function MemberNode({ data }: NodeProps<SetNode>) {
  const { member: m, inputs } = data;
  return (
    <div className={`set-node${m.missing ? ' missing' : ''}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="set-node-head">
        <b>{m.name ?? m.concept}</b>
        {m.visibility && m.visibility !== 'official' ? (
          <span className="chip">{VIS[m.visibility] ?? m.visibility}</span>
        ) : null}
      </div>
      {m.missing ? (
        <div className="faint small">Not available to you</div>
      ) : (
        <>
          <div className="faint small">
            {m.fieldCount ?? 0} fields{m.version ? ` · v${m.version}` : ''}
          </div>
          <div className="set-node-cov">
            {inputs.map((a) => {
              const c = m.coverage?.[a.id];
              return c ? (
                <span key={a.id} title={`${a.shortName}: ${c.mapped} of ${c.total} fields`}>
                  <ApiAvatar text={a.logo.text} color={a.logo.color} size={16} />
                  <span className="mono small">
                    {c.mapped}/{c.total}
                  </span>
                </span>
              ) : null;
            })}
          </div>
        </>
      )}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes: NodeTypes = { member: MemberNode };

/** Fits the view to what the control box leaves free, when it opens or closes. */
function Refit({ inset }: { inset: number }) {
  const rf = useReactFlow();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void rf.fitView({ padding: fitPadding(inset, 0.1), maxZoom: 1, duration: 250 });
    // only the box opening or closing moves the view
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inset]);
  return null;
}

/** Brings the view to a node or relation picked from the list. */
function FocusOn({ ids, nonce, inset }: { ids: string[]; nonce: number; inset: number }) {
  const rf = useReactFlow();
  useEffect(() => {
    if (nonce === 0 || ids.length === 0) return;
    void rf.fitView({
      nodes: ids.map((id) => ({ id })),
      padding: fitPadding(inset, 0.25),
      maxZoom: 1,
      duration: 350,
    });
    // only a pick from the list moves the view; a click on the canvas must not
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce]);
  return null;
}

/**
 * The top level of a model set: the models as boxes and the relations as arrows (solid = decided, dashed = a
 * proposal), like a database diagram. Click a box or an arrow to see it beside the diagram.
 */
export function SetDiagram({
  set,
  selection,
  onSelect,
  checked,
  text,
  inset,
  height,
  focusNonce,
}: {
  set: ModelSet;
  /** "m:<concept>" or "r:<relation id>" */
  selection: string | null;
  onSelect: (sel: string) => void;
  checked: ReadonlySet<string> | null;
  text: string;
  inset: number;
  height: string;
  focusNonce: number;
}) {
  const { theme } = useTheme();
  const base = useMemo(() => layoutSet(set), [set]);
  const dim = useMemo(() => dimmingSet(set, { checked, text }), [set, checked, text]);
  const nodes = useMemo(
    () =>
      base.nodes.map((n) => ({
        ...n,
        className: dim.nodes.has(n.id) ? 'dim' : undefined,
        selected: n.id === selection,
      })),
    [base.nodes, dim, selection],
  );
  const edges = useMemo(
    () =>
      base.edges.map((e) => {
        const off = dim.edges.has(e.id);
        const on = e.id === selection;
        return {
          ...e,
          selected: on,
          className: off ? 'dim' : undefined,
          style: {
            ...e.style,
            strokeWidth: on ? 3.6 : e.style?.strokeWidth,
            opacity: off ? (on ? 0.5 : 0.16) : 1,
          },
          labelBgStyle: { fill: 'var(--surface)', stroke: 'var(--line)' },
          labelStyle: { ...e.labelStyle, fill: 'var(--ink)' },
        };
      }),
    [base.edges, dim, selection],
  );
  const focusIds = useMemo(() => {
    if (!selection) return [];
    if (selection.startsWith('m:')) return [selection];
    const e = base.edges.find((x) => x.id === selection);
    return e ? [e.source, e.target] : [];
  }, [selection, base.edges]);

  return (
    <div
      className="flow"
      style={{ '--flow-h': height } as CSSProperties}
      role="group"
      aria-label="Model set diagram (the same models and relations are in the control box, as a list)"
    >
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: fitPadding(inset, 0.1), maxZoom: 1 }}
          minZoom={0.2}
          maxZoom={1.6}
          nodesConnectable={false}
          nodesDraggable={false}
          elementsSelectable
          zoomOnScroll={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, n) => onSelect(n.id)}
          onEdgeClick={(_, e) =>
            onSelect(
              (e.data as RelationEdgeData | undefined)
                ? relationId((e.data as RelationEdgeData).relationId)
                : e.id,
            )
          }
        >
          <FocusOn ids={focusIds} nonce={focusNonce} inset={inset} />
          <Refit inset={inset} />
          <Background gap={22} size={1.5} />
          <MiniMap
            pannable
            zoomable
            position="bottom-right"
            style={{ right: 64, width: 160, height: 100 }}
            ariaLabel="Mini map of the model set"
          />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}

export { memberId };
