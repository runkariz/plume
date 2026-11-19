import { useState } from 'react';
import type { RuleSource } from '@/api/types';
import { safeHref } from '@/pages/maintainer/release/notes';
import { Card } from './Card';
import { Chip } from './Chip';

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

/** How long a rule's text is before it is cut (the whole rule is in the document's text). */
const TEXT_AT_MOST = 120;

/** The rule's text on one line, cut with an ellipsis after about 120 characters (at a word when it can). */
export function shortRule(text: string): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= TEXT_AT_MOST) return t;
  const cut = t.slice(0, TEXT_AT_MOST);
  const space = cut.lastIndexOf(' ');
  return `${(space > TEXT_AT_MOST * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/** The pages of a rule, without repeats and without empty entries. */
export function rulePages(r: RuleSource): string[] {
  return Array.from(
    new Set((r.urls ?? []).filter((u) => typeof u === 'string' && u.trim() !== '')),
  );
}

interface Rule {
  id: string;
  text: string | null;
  type: string | null;
}

function RulePages({ rule, pages }: { rule: Rule; pages: string[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? pages : pages.slice(0, SHOWN);
  return (
    <div>
      <p className="rule-text" title={rule.id}>
        {rule.text ? shortRule(rule.text) : <span className="mono small">{rule.id}</span>}
        {rule.type ? <Chip>{rule.type}</Chip> : null}
      </p>
      <p className="rule-count">
        <b>Stated on {pages.length} pages</b>
      </p>
      <ul
        className="linked-list"
        aria-label={`Pages of ${rule.text ? shortRule(rule.text) : `rule ${rule.id}`}`}
      >
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
    return pages.length > 1
      ? [{ rule: { id: r.ruleId, text: r.text?.trim() || null, type: r.type || null }, pages }]
      : [];
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
          <RulePages key={r.rule.id} rule={r.rule} pages={r.pages} />
        ))}
      </div>
    </Card>
  );
}
