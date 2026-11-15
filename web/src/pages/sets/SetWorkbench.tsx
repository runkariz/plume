import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import type { ModelSet } from '@/api/types';
import { Card } from '@/components';
import { useMedia } from '@/lib/useMedia';
import { ControlBox, CONTROLS_W } from '@/pages/models/ControlBox';
import { SetDiagram } from './SetDiagram';
import { controlItems } from './setGraph';

const WIDE = '(min-width: 721px)';
/** The control box starts open on a desktop screen and closed below it; the person can toggle it any time. */
export const SET_OPEN_FROM = '(min-width: 1400px)';

/**
 * The diagram of a model set with what is needed to work with it, without scrolling: the control box over its left
 * (filter, APIs, a keyboard list of models and relations) and the detail beside it (below on a narrow screen).
 * It takes the state (filter, checked APIs, selection) as props and the detail as children, so the page (with the
 * editor) and the embedded view (read only) share it.
 */
export function SetWorkbench({
  set,
  text,
  show,
  selection,
  onText,
  onToggleApi,
  onSelect,
  canvasHeight,
  children,
}: {
  set: ModelSet;
  text: string;
  show: string[] | null;
  selection: string | null;
  onText: (text: string) => void;
  onToggleApi: (apiId: string, on: boolean) => void;
  onSelect: (selection: string) => void;
  canvasHeight: string;
  children: ReactNode;
}) {
  const wide = useMedia(WIDE, true);
  const roomy = useMedia(SET_OPEN_FROM, true);
  const [openChoice, setOpenChoice] = useState<boolean | null>(null);
  const open = openChoice ?? roomy;
  const inset = open && wide ? CONTROLS_W + 12 : 0;
  const [focusNonce, setFocusNonce] = useState(0);
  const checked = useMemo(() => (show ? new Set(show) : null), [show]);
  const items = useMemo(
    () => controlItems(set, text, selection, checked),
    [set, text, selection, checked],
  );
  return (
    <div className="workbench" style={{ '--wb-h': canvasHeight } as CSSProperties}>
      <div className="wb-canvas">
        <SetDiagram
          set={set}
          selection={selection}
          onSelect={onSelect}
          checked={checked}
          text={text}
          inset={inset}
          height="var(--wb-h)"
          focusNonce={focusNonce}
        />
        <ControlBox
          label="Diagram controls"
          toggleLabel="Filter models and relations"
          listLabel="Models and relations"
          filterPlaceholder="Model or relation"
          note="Unchecked APIs stay in the diagram, greyed out."
          noun="model or relation"
          apis={set.inputs}
          items={items}
          total={set.members.length + set.relations.length}
          text={text}
          checked={checked}
          open={open}
          onOpenChange={setOpenChoice}
          onText={onText}
          onToggleApi={onToggleApi}
          onPick={(sel) => {
            onSelect(sel);
            setFocusNonce((n) => n + 1);
          }}
        />
      </div>
      <Card
        className="pad wb-detail"
        role="region"
        aria-label="Selected model or relation"
        tabIndex={0}
      >
        {children}
      </Card>
    </div>
  );
}
