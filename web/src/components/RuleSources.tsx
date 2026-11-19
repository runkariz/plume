import { useState } from 'react';
import type { RuleSource } from '@/api/types';
import { safeHref } from '@/pages/maintainer/release/notes';
import { Card } from './Card';

/** How many pages of a rule are listed before "Show all". */
const SHOWN = 3;

/** A page address for people: host and path, no scheme; the whole address stays in the link's title. */
export function pageLabel(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname === '/' ? '' : u.pathname.replace(/\/$/, '');
    return `${u.host}${path}${u.hash}`;
  } catch {
    return url;
  }
}

/** The pages of a rule, without repeats and without empty entries. */
export function rulePages(r: RuleSource): string[] {
  return Array.from(
    new Set((r.urls ?? []).filter((u) => typeof u === 'string' && u.trim() !== '')),
  );
}

function RulePages({ rule, pages }: { rule: string; pages: string[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? pages : pages.slice(0, SHOWN);
  return (
    <div>
      <p className="rule-count">
        <span className="mono faint small">{rule}</span> <b>Stated on {pages.length} pages</b>
      </p>
      <ul className="linked-list" aria-label={`Pages of rule ${rule}`}>
        {shown.map((u) => {
          const href = safeHref(u);
          return (
            <li key={u}>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer noopener" title={u}>
                  {pageLabel(u)}
                </a>
              ) : (
                <span className="mono small">{u}</span>
              )}
            </li>
          );
        })}
      </ul>
      {pages.length > SHOWN ? (
        <div className="show-all">
          <button type="button" className="linkbtn" onClick={() => setAll((v) => !v)}>
            {all ? `Show the first ${SHOWN}` : `Show all ${pages.length}`}
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The rules of a document's text that the package states on more than one documentation page, each with its pages
 * (the first three, then "Show all"). A rule with one page, and a document without `ruleSources`, show nothing.
 */
export function RuleSources({ sources }: { sources: RuleSource[] | undefined }) {
  const rules = (sources ?? []).flatMap((r) => {
    const pages = rulePages(r);
    return pages.length > 1 ? [{ id: r.ruleId, pages }] : [];
  });
  if (rules.length === 0) return null;
  return (
    <Card className="pad rule-sources" role="region" aria-label="Rule sources">
      <h2 className="h2-sm">Rules stated on several pages</h2>
      <p className="muted small">
        The rules in the text below that the vendor documents on more than one page.
      </p>
      <div className="rule-list">
        {rules.map((r) => (
          <RulePages key={r.id} rule={r.id} pages={r.pages} />
        ))}
      </div>
    </Card>
  );
}
