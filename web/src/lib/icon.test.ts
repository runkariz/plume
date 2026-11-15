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
    expect(iconSrc(null)).toBeNull();
    expect(iconSrc(undefined)).toBeNull();
  });
});
