import type { ModelSnapshot } from '@/api/types';
import { ControlBox, CONTROLS_W, type ControlItem } from './ControlBox';
import { rowMatches, type MappingRow, type Selection } from './graph';

export { CONTROLS_W };

/**
 * The control box of the mapping graph: the list holds the mappings (a canonical field and one API that fills it).
 * See ControlBox for the behaviour.
 */
export function GraphControls({
  snap,
  rows,
  selection,
  text,
  checked,
  open,
  onOpenChange,
  onText,
  onToggleApi,
  onSelect,
}: {
  snap: ModelSnapshot;
  rows: MappingRow[];
  selection: Selection | null;
  text: string;
  /** null = every API is checked */
  checked: ReadonlySet<string> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onText: (text: string) => void;
  onToggleApi: (apiId: string, on: boolean) => void;
  onSelect: (s: Selection) => void;
}) {
  const key = (r: MappingRow) => `${r.field}|${r.apiId}`;
  const items: ControlItem[] = rows
    .filter((r) => rowMatches(r, text))
    .map((r) => ({
      id: key(r),
      name: r.field,
      detail: `← ${r.apiName}${r.kind === 'derived' ? ' (derived)' : ''}`,
      depth: r.depth,
      avatar: { apiId: r.apiId, kind: r.kind === 'derived' ? 'derived' : 'direct' },
      selected: Boolean(selection && r.field === selection.field && r.apiId === selection.apiId),
      off: checked !== null && !checked.has(r.apiId),
      title: `${r.field} ← ${r.apiName}`,
    }));
  return (
    <ControlBox
      label="Graph controls"
      toggleLabel="Filter and mappings"
      listLabel="Mappings"
      filterPlaceholder="Field or source path"
      note="Unchecked APIs stay in the graph, greyed out."
      noun="mapping"
      apis={snap.inputs}
      items={items}
      total={rows.length}
      text={text}
      checked={checked}
      open={open}
      onOpenChange={onOpenChange}
      onText={onText}
      onToggleApi={onToggleApi}
      onPick={(id) => {
        const r = rows.find((x) => key(x) === id);
        if (r) onSelect({ field: r.field, apiId: r.apiId });
      }}
    />
  );
}
