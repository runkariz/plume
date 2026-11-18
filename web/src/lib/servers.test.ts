import { resolveServers, serverLabel, serverRows } from './servers';

describe('serverLabel', () => {
  it('names the roles for people and leaves unknown keys as written', () => {
    expect(serverLabel('api')).toBe('API');
    expect(serverLabel('auth')).toBe('Auth');
    expect(serverLabel('auth_2')).toBe('Auth 2');
    expect(serverLabel('api_6')).toBe('API 6');
    expect(serverLabel('upload')).toBe('upload');
    expect(serverLabel('api_x')).toBe('api_x');
  });
});

describe('serverRows', () => {
  it('puts the base URL first, then the other servers in the package order', () => {
    const rows = serverRows({
      baseUrl: 'https://api.x.com',
      servers: {
        auth: 'https://login.x.com',
        api: 'https://api.x.com',
        auth_2: 'https://a2.x.com',
      },
    });
    expect(rows.map((r) => [r.label, r.url])).toEqual([
      ['API', 'https://api.x.com'],
      ['Auth', 'https://login.x.com'],
      ['Auth 2', 'https://a2.x.com'],
    ]);
  });
  it('shows a base URL that is none of the servers first and unlabelled', () => {
    const rows = serverRows({ baseUrl: 'https://b', servers: { auth: 'https://a' } });
    expect(rows).toEqual([
      { key: null, label: null, url: 'https://b' },
      { key: 'auth', label: 'Auth', url: 'https://a' },
    ]);
  });
  it('shows the base URL alone without servers, and nothing without either', () => {
    expect(serverRows({ baseUrl: 'https://b' })).toHaveLength(1);
    expect(serverRows({})).toEqual([]);
  });
  it('skips servers that are not text', () => {
    expect(
      serverRows({ servers: { api: 'https://a', api_2: 5 as unknown as string, auth: '' } }),
    ).toHaveLength(1);
  });
});

describe('resolveServers', () => {
  const servers = { api: 'https://api.bol.com', auth: 'https://login.bol.com' };
  it('puts the environment server into the template', () => {
    expect(resolveServers('{{app_env.servers.auth}}/token', servers)).toBe(
      'https://login.bol.com/token',
    );
  });
  it('returns null when the template names no server or a server the environment lacks', () => {
    expect(resolveServers('https://x/token', servers)).toBeNull();
    expect(resolveServers('{{app_env.servers.auth_2}}/token', servers)).toBeNull();
    expect(resolveServers('{{app_env.servers.auth}}/token', undefined)).toBeNull();
    expect(resolveServers('{{app_env.servers.constructor}}/x', servers)).toBeNull();
  });
  it('leaves other variables as written', () => {
    expect(resolveServers('{{app_env.servers.api}}/{{req_vars.id}}', servers)).toBe(
      'https://api.bol.com/{{req_vars.id}}',
    );
  });
});
