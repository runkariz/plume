import { useEffect, useState } from 'react';
import type { ApiRef, SuggestResponse } from '@/api/types';
import { ApiAvatar, Button, Segmented } from '@/components';
import { changed, isFiltered, PAGE_SIZE, type Chip, type SuggestView } from './suggestQuery';

/**
 * The filters of the suggestions page, all kept in the URL by the page: a search box, one checkbox per selected API
 * ("only concepts that exist in every checked API", direct or derived), the scope (shared by several APIs, or found
 * in only one) and the chips All / In all N / Can write. They combine; counts come from the server.
 */
export function SuggestControls({
  apis,
  view,
  counts,
  onChange,
  onClear,
  clearSignal,
}: {
  apis: ApiRef[];
  view: SuggestView;
  counts: SuggestResponse['counts'] | null;
  /** The change is applied to the latest view, so two quick clicks both count. */
  onChange: (update: (v: SuggestView) => SuggestView) => void;
  onClear: () => void;
  /** Changes when the page clears the filters from elsewhere: the search box empties too. */
  clearSignal: number;
}) {
  const [draft, setDraft] = useState(view.q);
  const [seenClear, setSeenClear] = useState(clearSignal);
  if (seenClear !== clearSignal) {
    setSeenClear(clearSignal);
    setDraft('');
  }
  // the URL follows the box a moment after the last key, so typing does not fire a request per letter
  useEffect(() => {
    if (draft.trim() === view.q) return;
    const q = draft.trim();
    const t = setTimeout(() => onChange((v) => changed(v, { q })), 300);
    return () => clearTimeout(t);
  }, [draft, view, onChange]);

  const n = (v: number | undefined) => (v === undefined ? '' : ` · ${v}`);
  const shared = view.only !== 'single';
  return (
    <section className="suggest-controls" aria-label="Filter the concepts">
      <div className="suggest-search">
        <label htmlFor="concept-search" className="sr-only">
          Search concepts
        </label>
        <input
          id="concept-search"
          type="search"
          className="input"
          placeholder="Search concepts by name or reason"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          autoComplete="off"
        />
      </div>
      <fieldset className="suggest-require">
        <legend>Only concepts that exist in</legend>
        {apis.map((a) => (
          <label key={a.id} className={view.require.includes(a.id) ? 'on' : undefined}>
            <input
              type="checkbox"
              checked={view.require.includes(a.id)}
              onChange={(e) =>
                onChange((v) =>
                  changed(v, {
                    require: e.target.checked
                      ? [...v.require.filter((id) => id !== a.id), a.id]
                      : v.require.filter((id) => id !== a.id),
                  }),
                )
              }
            />
            <ApiAvatar text={a.logo.text} color={a.logo.color} url={a.logo.url} size={20} />
            <span>{a.shortName}</span>
          </label>
        ))}
      </fieldset>
      <div className="opts">
        <Segmented
          variant="pills"
          label="Concepts"
          value={view.only === 'single' ? 'single' : 'multi'}
          onChange={(only) => onChange((v) => changed(v, { only }))}
          options={[
            { value: 'multi', label: `Shared by several APIs${n(counts?.all)}` },
            { value: 'single', label: `Only in one API${n(counts?.single)}` },
          ]}
        />
        {shared ? (
          <Segmented<Chip>
            variant="pills"
            label="Show concepts"
            value={view.chip}
            onChange={(chip) => onChange((v) => changed(v, { chip }))}
            options={[
              { value: 'all', label: `All concepts${n(counts?.all)}` },
              { value: 'every', label: `In all ${apis.length} APIs${n(counts?.inAll)}` },
              { value: 'write', label: `Can write${n(counts?.write)}` },
            ]}
          />
        ) : null}
        {isFiltered(view) ? (
          <button type="button" className="linkbtn small" onClick={onClear}>
            Clear filters
          </button>
        ) : null}
      </div>
    </section>
  );
}

/** "Showing 25–48 of 61 concepts" with Previous / Next (the page number is in the URL). */
export function Pager({
  data,
  page,
  onPage,
}: {
  data: SuggestResponse;
  page: number;
  onPage: (p: number) => void;
}) {
  const first = data.total === 0 ? 0 : data.offset + 1;
  const last = data.offset + data.concepts.length;
  const pages = Math.max(1, Math.ceil(data.total / (data.limit || PAGE_SIZE)));
  if (data.total <= (data.limit || PAGE_SIZE) && page === 1)
    return (
      <p className="muted small pager-text" aria-live="polite">
        {data.total} {data.total === 1 ? 'concept' : 'concepts'}
      </p>
    );
  return (
    <nav className="pager" aria-label="Pages of concepts">
      <span className="muted small" aria-live="polite">
        Showing {first}–{last} of {data.total} concepts · page {page} of {pages}
      </span>
      <span className="row">
        <Button disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button disabled={data.nextOffset === null} onClick={() => onPage(page + 1)}>
          Next
        </Button>
      </span>
    </nav>
  );
}
