import type { Environment } from '@/api/types';

/**
 * A package names the hosts of an environment by role: "api", "auth", and "api_2", "auth_2" ... when it needs more
 * than one of a kind. The label is the role for people ("API", "Auth", "API 2"); a key this app does not know is
 * shown as the package wrote it.
 */
export function serverLabel(key: string): string {
  const m = /^(api|auth)(?:_(\d+))?$/.exec(key);
  if (!m) return key;
  const role = m[1] === 'api' ? 'API' : 'Auth';
  return m[2] ? `${role} ${m[2]}` : role;
}

/** One host of an environment, ready to show: the label and the URL as the package wrote it (a template stays one). */
export interface ServerRow {
  key: string | null;
  label: string | null;
  url: string;
}

/**
 * The hosts of an environment, base URL first (as before servers were shown): the server whose URL is the base URL
 * comes first with its role, then the others in the order the package lists them. A base URL that is none of the
 * servers is shown first without a label; an environment without servers shows its base URL alone, as it always did.
 */
export function serverRows(e: Pick<Environment, 'baseUrl' | 'servers'>): ServerRow[] {
  const servers = Object.entries(e.servers ?? {}).filter(
    (kv): kv is [string, string] => typeof kv[1] === 'string' && kv[1] !== '',
  );
  const base = typeof e.baseUrl === 'string' && e.baseUrl ? e.baseUrl : null;
  const first = base ? servers.findIndex(([, url]) => url === base) : -1;
  const rows: ServerRow[] = servers.map(([key, url]) => ({ key, label: serverLabel(key), url }));
  if (first > 0) rows.unshift(...rows.splice(first, 1));
  if (base && first < 0) rows.unshift({ key: null, label: null, url: base });
  return rows;
}

const SERVER_REF = /\{\{\s*app_env\.servers\.([A-Za-z0-9_]+)\s*\}\}/g;

/** Whether a URL template names a server of the environment ("{{app_env.servers.auth}}/token"). */
export function usesServers(template: string): boolean {
  return new RegExp(SERVER_REF.source).test(template);
}

/**
 * The template with the environment's servers put in. Null when it names no server, or when a server it names is
 * not one of this environment's (then nothing is guessed). Other variables ({{app_env.vars.host}}) stay as written.
 */
export function resolveServers(
  template: string,
  servers: Record<string, string> | undefined,
): string | null {
  if (!usesServers(template) || !servers) return null;
  let missing = false;
  const out = template.replace(SERVER_REF, (_all, key: string) => {
    const url = Object.prototype.hasOwnProperty.call(servers, key) ? servers[key] : undefined;
    if (typeof url !== 'string' || !url) {
      missing = true;
      return '';
    }
    return url;
  });
  return missing ? null : out;
}
