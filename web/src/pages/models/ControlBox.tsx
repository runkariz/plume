import { useEffect, useId, useState, type KeyboardEvent } from 'react';
import type { ApiRef } from '@/api/types';
import { ApiAvatar } from '@/components';

/** Width of the control box over a canvas, in px (a graph fits to what is left of it). */
export const CONTROLS_W = 272;

/** One row of the list in the control box. */
export interface ControlItem {
  /** Unique among the rows. */
  id: string;
  name: string;
  /** Shown after the name, smaller ("← Shopify (derived)"). */
  detail?: string;
  /** Indents the row (nested fields). */
  depth?: number;
  /** An avatar of an API in front of the row, drawn like the coverage circles. */
  avatar?: { apiId: string; kind: 'direct' | 'derived' | 'absent' };
  selected: boolean;
  /** Greyed out (its API is unchecked); the row stays in the list. */
  off?: boolean;
  title?: string;
}

/**
 * The control box over the left of a canvas, collapsible: a filter by name, one checkbox per API (an unchecked API
 * is greyed out on the canvas, never hidden), and a list that is also the keyboard way into the canvas. It knows
 * nothing about what the rows are: the mapping graph and the model-set diagram both use it. What it changes is
 * kept by the caller (the page keeps it in the URL).
 */
export function ControlBox({
  label,
  toggleLabel,
  listLabel,
  filterPlaceholder,
  note,
  noun,
  apis,
  items,
  total,
  text,
  checked,
  open,
  onOpenChange,
  onText,
  onToggleApi,
  onPick,
}: {
  /** The accessible name of the box ("Graph controls"). */
  label: string;
  toggleLabel: string;
  listLabel: string;
  filterPlaceholder: string;
  /** Under the checkboxes ("Unchecked APIs stay in the graph, greyed out."). */
  note: string;
  /** What the list holds, for "No mapping matches": "mapping". */
  noun: string;
  apis: ApiRef[];
  /** The rows to show (the caller applies the name filter). */
  items: ControlItem[];
  /** How many rows there are without the filter. */
  total: number;
  text: string;
  /** null = every API is checked */
  checked: ReadonlySet<string> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onText: (text: string) => void;
  onToggleApi: (apiId: string, on: boolean) => void;
  onPick: (id: string) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(text);
  // the caller follows the box a moment after the last key
  useEffect(() => {
    if (draft.trim() === text) return;
    const t = setTimeout(() => onText(draft.trim()), 250);
    return () => clearTimeout(t);
  }, [draft, text, onText]);

  const [active, setActive] = useState(0);
  const idx = Math.max(0, Math.min(active, items.length - 1));
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
    const last = items.length - 1;
    const go = (n: number) => {
      e.preventDefault();
      setActive(Math.max(0, Math.min(last, n)));
    };
    if (e.key === 'ArrowDown') go(idx + 1);
    else if (e.key === 'ArrowUp') go(idx - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(last);
    else if ((e.key === 'Enter' || e.key === ' ') && items[idx]) {
      e.preventDefault();
      onPick(items[idx].id);
    }
  }

  const isOn = (apiId: string) => checked === null || checked.has(apiId);
  return (
    <aside className={`wb-controls${open ? ' open' : ''}`} aria-label={label}>
      <button
        type="button"
        className="wb-controls-toggle"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={() => onOpenChange(!open)}
      >
        <span aria-hidden>{open ? '‹' : '›'}</span> {toggleLabel}
      </button>
      <div id={`${id}-body`} className="wb-controls-body" hidden={!open}>
        <div className="wb-field">
          <label htmlFor={`${id}-filter`}>Filter by name</label>
          <input
            id={`${id}-filter`}
            type="search"
            className="input"
            placeholder={filterPlaceholder}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoComplete="off"
          />
        </div>
        <fieldset className="wb-apis">
          <legend>APIs</legend>
          {apis.map((a) => {
            const on = isOn(a.id);
            const onlyOne = on && apis.filter((x) => isOn(x.id)).length === 1;
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
          <p className="faint small">{note}</p>
        </fieldset>
        <div className="wb-list-head">
          <span id={`${id}-list-label`}>{listLabel}</span>
          <span className="faint small" aria-live="polite">
            {items.length} of {total}
          </span>
        </div>
        {items.length === 0 ? (
          <p className="muted small">
            No {noun} matches “{text}”.
          </p>
        ) : (
          <ul
            className="wb-list"
            role="listbox"
            aria-labelledby={`${id}-list-label`}
            tabIndex={0}
            aria-activedescendant={optId(idx)}
            onKeyDown={key}
          >
            {items.map((r, i) => {
              const api = r.avatar ? apis.find((a) => a.id === r.avatar?.apiId) : undefined;
              return (
                // keyboard: the listbox handles Arrow, Home, End, Enter and Space for all its options
                // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                <li
                  key={r.id}
                  id={optId(i)}
                  role="option"
                  aria-selected={r.selected}
                  className={[r.selected ? 'sel' : '', i === idx ? 'act' : '', r.off ? 'off' : '']
                    .filter(Boolean)
                    .join(' ')}
                  style={{ paddingLeft: 8 + Math.min(r.depth ?? 0, 3) * 12 }}
                  onClick={() => {
                    setActive(i);
                    onPick(r.id);
                  }}
                >
                  {api && r.avatar ? (
                    <ApiAvatar
                      text={api.logo.text}
                      color={api.logo.color}
                      url={api.logo.url}
                      kind={r.avatar.kind}
                      size={16}
                    />
                  ) : null}
                  <span
                    className="wb-row-text"
                    title={r.title ?? `${r.name} ${r.detail ?? ''}`.trim()}
                  >
                    <span className="mono wb-row-name">{r.name}</span>{' '}
                    {r.detail ? <span className="faint small wb-row-api">{r.detail}</span> : null}
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
