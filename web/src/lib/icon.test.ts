import { iconSrc } from './icon';

describe('iconSrc', () => {
  it('turns the API-relative icon path into a URL on the API', () => {
    expect(iconSrc('/v1/apis/shopify/icon', 'http://127.0.0.1:18490')).toBe(
      'http://127.0.0.1:18490/v1/apis/shopify/icon',
    );
  });
  it('refuses everything that is not a path on the API: the web never loads third-party images', () => {
    for (const bad of [
      'https://shopify.dev/favicon.ico',
      'http://evil.example/x.png',
      '//evil.example/x.png',
      'data:image/png;base64,AAAA',
      'javascript:alert(1)',
      '/static/logo.png',
      '/v1/../secret',
      '',
    ])
      expect(iconSrc(bad, 'http://127.0.0.1:18490'), bad).toBeNull();
    expect(iconSrc(null, 'http://127.0.0.1:18490')).toBeNull();
    expect(iconSrc(undefined, 'http://127.0.0.1:18490')).toBeNull();
  });
  it('shows nothing without an API base to load from (the embedded view has none)', () => {
    expect(iconSrc('/v1/apis/shopify/icon')).toBeNull();
    expect(iconSrc('/v1/apis/shopify/icon', null)).toBeNull();
  });
  it('on the same origin (an empty base) the icon is a relative /v1 path, still only on the API', () => {
    expect(iconSrc('/v1/apis/shopify/icon', '')).toBe('/v1/apis/shopify/icon');
    expect(iconSrc('https://shopify.dev/favicon.ico', '')).toBeNull();
    expect(iconSrc('//evil.example/x.png', '')).toBeNull();
    expect(iconSrc('/v1/../secret', '')).toBeNull();
  });
});
