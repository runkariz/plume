import { NavLink } from 'react-router-dom';

/** The two kinds of reports readers' LLMs make: questions and mappings of canonical models (maintainer). */
export function ReportsTabs() {
  return (
    <nav className="reports-tabs" aria-label="Kinds of reports">
      <NavLink to="/maintainer/reports" end className={({ isActive }) => (isActive ? 'on' : '')}>
        Reported questions
      </NavLink>
      <NavLink
        to="/maintainer/mapping-reports"
        className={({ isActive }) => (isActive ? 'on' : '')}
      >
        Mapping reports
      </NavLink>
    </nav>
  );
}
