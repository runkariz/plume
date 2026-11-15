import '@xyflow/react/dist/style.css';
import { useMemo } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
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

export function MappingGraph({
  snapshot,
  selection,
  onSelect,
}: {
  snapshot: ModelSnapshot;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) {
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
      role="group"
      aria-label="Mapping graph (also available as the Mapping list below)"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        colorMode={theme}
        fitView
        fitViewOptions={{ padding: 0.06 }}
        minZoom={0.3}
        maxZoom={1.6}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable
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
