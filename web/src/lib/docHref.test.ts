import { docHref, operationOf } from './docHref';

describe('operationOf (two operations at one METHOD + path)', () => {
  const id = 'endpoint:GET~/{file_path}@get-or15';
  it('is the part after "@" of an endpoint id that continues the method and path of its own document', () => {
    expect(operationOf(id, 'GET', '/{file_path}')).toBe('get-or15');
    expect(operationOf('endpoint:GET~/{file_path}@get-of54', 'GET', '/{file_path}')).toBe(
      'get-of54',
    );
  });
  it('is null for an id without one, whatever the other ids look like', () => {
    expect(operationOf('endpoint:GET~/orders', 'GET', '/orders')).toBeNull();
    expect(operationOf('model:order', null, null)).toBeNull();
    expect(operationOf('guide:rate-limits', 'GET', '/x')).toBeNull();
    expect(operationOf(null, 'GET', '/x')).toBeNull();
    expect(operationOf(id, null, '/{file_path}')).toBeNull();
    expect(operationOf(id, 'GET', null)).toBeNull();
  });
  it('does not take an "@" that belongs to the path (/users/@me) for an operation', () => {
    expect(operationOf('endpoint:GET~/users/@me', 'GET', '/users/@me')).toBeNull();
    expect(operationOf('endpoint:GET~/users/@me@get-x', 'GET', '/users/@me')).toBe('get-x');
  });
  it('a document of another method or path does not borrow the suffix', () => {
    expect(operationOf(id, 'POST', '/{file_path}')).toBeNull();
    expect(operationOf(id, 'GET', '/other')).toBeNull();
    expect(operationOf('endpoint:GET~/{file_path}@', 'GET', '/{file_path}')).toBeNull();
  });
  it('the id is encoded in links: braces, slash, tilde and "@" cannot break the route', () => {
    expect(docHref('mirakl', id)).toBe(`/apis/mirakl/documents/${encodeURIComponent(id)}`);
    expect(docHref('mirakl', id)).toContain('%40get-or15');
    expect(docHref('mirakl', id)).not.toContain('{');
  });
});
