import { useEffect, useId, useState, type KeyboardEvent } from 'react';
import type { ModelSnapshot } from '@/api/types';
import { ApiAvatar } from '@/components';
import { rowMatches, type MappingRow, type Selection } from './graph';

/** Width of the control box over the canvas, in px (the graph fits to what is left of it). */
export const CONTROLS_W = 272;

/**
 * The control box over the left of the canvas, collapsible: a filter by name (canonical field or source path), one
 * checkbox per API (an unchecked API is greyed out in the graph, never hidden), and the list of mappings, which is
 * also the keyboard way into the graph. Everything it changes is kept in the URL by the page.
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
  const id = useId();
  const [draft, setDraft] = useState(text);
  // the URL follows the box a moment after the last key
  useEffect(() => {
    if (draft.trim() === text) return;
    const t = setTimeout(() => onText(draft.trim()), 250);
    return () => clearTimeout(t);
  }, [draft, text, onText]);

  const visible = rows.filter((r) => rowMatches(r, text));
  const selectedIndex = visible.findIndex(
    (r) => selection && r.field === selection.field && r.apiId === selection.apiId,
  );
  const [active, setActive] = useState(0);
  const idx = Math.max(0, Math.min(active, visible.length - 1));
  const optId = (i: number) => `${id}-opt-${i}`;
  useEffect(() => {
    if (!open) return;
    // keep the highlighted row inside the LIST: scroll the list itself, never the page or the box around it
    const el = document.getElementById(optId(idx));
    const list = el?.parentElement;
    if (!el || !list) return;
    if (el.offsetTop < list.scrollTop) list.scrollTop = el.offsetTop;
    else if (el.offsetTop + el.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = el.offsetTop + el.offsetHeight - list.clientHeight;
    // the highlighted row stays in view while moving with the arrow keys
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, open]);

  function key(e: KeyboardEvent<HTMLUListElement>) {
    const last = visible.length - 1;
    const go = (n: number) => {
      e.preventDefault();
      setActive(Math.max(0, Math.min(last, n)));
    };
    if (e.key === 'ArrowDown') go(idx + 1);
    else if (e.key === 'ArrowUp') go(idx - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(last);
    else if ((e.key === 'Enter' || e.key === ' ') && visible[idx]) {
      e.preventDefault();
      const r = visible[idx];
      onSelect({ field: r.field, apiId: r.apiId });
    }
  }

  const isOn = (apiId: string) => checked === null || checked.has(apiId);
  return (
    <aside className={`wb-controls${open ? ' open' : ''}`} aria-label="Graph controls">
      <button
        type="button"
        className="wb-controls-toggle"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={() => onOpenChange(!open)}
      >
        <span aria-hidden>{open ? '‹' : '›'}</span> Filter and mappings
      </button>
      <div id={`${id}-body`} className="wb-controls-body" hidden={!open}>
        <div className="wb-field">
          <label htmlFor={`${id}-filter`}>Filter by name</label>
          <input
            id={`${id}-filter`}
            type="search"
            className="input"
            placeholder="Field or source path"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoComplete="off"
          />
        </div>
        <fieldset className="wb-apis">
          <legend>APIs</legend>
          {snap.inputs.map((a) => {
            const on = isOn(a.id);
            const onlyOne = on && snap.inputs.filter((x) => isOn(x.id)).length === 1;
            return (
              <label key={a.id} className={on ? undefined : 'off'}>
                <input
                  type="checkbox"
                  checked={on}
                  disabled={onlyOne}
                  onChange={(e) => onToggleApi(a.id, e.target.checked)}
                />
                <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={20} />
                <span>{a.shortName}</span>
              </label>
            );
          })}
          <p className="faint small">Unchecked APIs stay in the graph, greyed out.</p>
        </fieldset>
        <div className="wb-list-head">
          <span id={`${id}-list-label`}>Mappings</span>
          <span className="faint small" aria-live="polite">
            {visible.length} of {rows.length}
          </span>
        </div>
        {visible.length === 0 ? (
          <p className="muted small">No mapping matches “{text}”.</p>
        ) : (
          <ul
            className="wb-list"
            role="listbox"
            aria-labelledby={`${id}-list-label`}
            tabIndex={0}
            aria-activedescendant={optId(idx)}
            onKeyDown={key}
          >
            {visible.map((r, i) => {
              const selected = i === selectedIndex;
              const on = isOn(r.apiId);
              const api = snap.inputs.find((a) => a.id === r.apiId);
              return (
                // keyboard: the listbox handles Arrow, Home, End, Enter and Space for all its options
                // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                <li
                  key={`${r.field}|${r.apiId}`}
                  id={optId(i)}
                  role="option"
                  aria-selected={selected}
                  className={[selected ? 'sel' : '', i === idx ? 'act' : '', on ? '' : 'off']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => {
                    setActive(i);
                    onSelect({ field: r.field, apiId: r.apiId });
                  }}
                >
                  {api ? (
                    <ApiAvatar
                      text={api.logo.text}
                      color={api.logo.color}
                      url={api.logo.url}
                      kind={r.kind === 'derived' ? 'derived' : 'direct'}
                      size={16}
                    />
                  ) : null}
                  <span className="wb-row-text" title={`${r.field} ← ${r.apiName}`}>
                    <span className="mono wb-row-name">{r.field}</span>{' '}
                    <span className="faint small wb-row-api">
                      ← {r.apiName}
                      {r.kind === 'derived' ? ' (derived)' : ''}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
