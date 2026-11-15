import { Link } from 'react-router-dom';

export interface Crumb {
  label: string;
  to?: string;
}

export function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${i}`}>
              {i > 0 ? <span aria-hidden>/</span> : null}
              {c.to && !last ? (
                <Link to={c.to}>{c.label}</Link>
              ) : (
                <b aria-current={last ? 'page' : undefined}>{c.label}</b>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
