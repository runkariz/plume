import { useMemo, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import type { ModelSnapshot } from '@/api/types';
import { Card } from '@/components';
import { CONTROLS_W, GraphControls } from './GraphControls';
import { mappingRows, type Selection } from './graph';
import { MappingDetail } from './MappingDetail';
import { MappingGraph } from './MappingGraph';

/** Whether a media query matches, known on the first render (no measuring, so nothing flickers or re-fits). */
function useMedia(query: string, fallback: boolean): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia?.(query);
      m?.addEventListener('change', cb);
      return () => m?.removeEventListener('change', cb);
    },
    () => window.matchMedia?.(query).matches ?? fallback,
    () => fallback,
  );
}

const WIDE = '(min-width: 721px)';
/**
 * The control box starts open on a desktop screen, where it leaves the graph enough room beside the detail panel,
 * and closed below this width; the person can open or close it at any time.
 */
export const OPEN_FROM = '(min-width: 1400px)';

/**
 * The graph with what is needed to work with it, without scrolling: the control box over its left (filter, APIs,
 * mapping list) and the detail of the selected mapping beside it (stacked below on a narrow screen). It takes the
 * model and the state (filter, checked APIs, selection) as props, so a page and an embedded view can both use it.
 */
export function ModelWorkbench({
  snap,
  scope,
  readable,
  text,
  show,
  selection,
  onText,
  onToggleApi,
  onSelect,
  renderDocLink,
  canvasHeight,
}: {
  snap: ModelSnapshot;
  scope: 'field' | 'all';
  /** A big model opens at a readable zoom and pans, instead of fitting everything. */
  readable: boolean;
  text: string;
  show: string[] | null;
  selection: Selection | null;
  onText: (text: string) => void;
  onToggleApi: (apiId: string, on: boolean) => void;
  onSelect: (s: Selection) => void;
  /** How a cited document is shown in the detail panel (a link in the web app, text when omitted). */
  renderDocLink?: (apiId: string, docId: string) => ReactNode;
  /**
   * A fixed canvas height. Without it the height follows the screen (vh): an embedded view must pass one, because
   * its own height is what the host sets from its content.
   */
  canvasHeight?: string;
}) {
  const wide = useMedia(WIDE, true);
  const roomy = useMedia(OPEN_FROM, true);
  const [openChoice, setOpenChoice] = useState<boolean | null>(null);
  const open = openChoice ?? roomy;
  const inset = open && wide ? CONTROLS_W + 12 : 0;
  const [focusNonce, setFocusNonce] = useState(0);
  const rows = useMemo(() => mappingRows(snap), [snap]);
  const checked = useMemo(() => (show ? new Set(show) : null), [show]);
  const dim = useMemo(() => ({ checked, text }), [checked, text]);

  // "Selected field": one field and the APIs that fill it
  const focusedField =
    scope === 'field' && selection
      ? snap.fields.find((f) => f.name === selection.field)
      : undefined;
  const graphSnap = focusedField
    ? {
        ...snap,
        fields: [focusedField],
        inputs: snap.inputs.filter(
          (a) => (focusedField.support[a.id] ?? 'unsupported') !== 'unsupported',
        ),
      }
    : snap;
  const height =
    canvasHeight ??
    (scope === 'field'
      ? 'clamp(400px, 50vh, 520px)'
      : readable
        ? 'clamp(560px, 82vh, 860px)'
        : 'clamp(520px, 78vh, 800px)');
  const empty = (scope === 'field' && !focusedField) || graphSnap.inputs.length === 0;

  return (
    <div className="workbench" style={{ '--wb-h': height } as CSSProperties}>
      <div className="wb-canvas">
        {empty ? (
          <div className="flow wb-empty">
            <p className="muted state">No API fills this field.</p>
          </div>
        ) : (
          <MappingGraph
            key={`${scope}:${focusedField?.name ?? 'all'}`}
            snapshot={graphSnap}
            selection={selection}
            onSelect={(s) => onSelect(s)}
            focusNonce={focusNonce}
            readable={readable && scope === 'all'}
            dim={dim}
            inset={inset}
            fit={scope === 'field' ? 'field' : 'all'}
            height="var(--wb-h)"
          />
        )}
        <GraphControls
          snap={snap}
          rows={rows}
          selection={selection}
          text={text}
          checked={checked}
          open={open}
          onOpenChange={setOpenChoice}
          onText={onText}
          onToggleApi={onToggleApi}
          onSelect={(s) => {
            onSelect(s);
            setFocusNonce((n) => n + 1); // a pick from the list also zooms the graph to it
          }}
        />
      </div>
      <Card className="pad wb-detail" role="region" aria-label="Mapping detail">
        {selection ? (
          <MappingDetail snap={snap} sel={selection} renderDocLink={renderDocLink} />
        ) : (
          <p className="muted">This model has no mapping to show.</p>
        )}
      </Card>
    </div>
  );
}
