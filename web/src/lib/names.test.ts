import { apiLabel, apiTitle } from './names';

describe('display names', () => {
  it('fixes brands with their own casing, whatever the server sent', () => {
    expect(apiLabel({ id: 'woocommerce', shortName: 'Woocommerce' })).toBe('WooCommerce');
    expect(apiLabel({ id: 'github', shortName: 'Github' })).toBe('GitHub');
    expect(apiTitle({ id: 'woocommerce', name: 'woocommerce' })).toBe('WooCommerce');
  });
  it('keeps the server short name when there is nothing to fix', () => {
    expect(apiLabel({ id: 'mirakl', shortName: 'Mirakl' })).toBe('Mirakl');
    expect(apiLabel({ id: 'test-catalog-api', shortName: 'Test' })).toBe('Test');
  });
  it('falls back to the title-cased id', () => {
    expect(apiLabel({ id: 'second-catalog-api' })).toBe('Second catalog api');
    expect(apiTitle({ id: 'shopify', name: 'shopify' })).toBe('Shopify');
  });
  it('keeps a real server name', () => {
    expect(apiTitle({ id: 'shopify', name: 'Shopify Admin REST API' })).toBe(
      'Shopify Admin REST API',
    );
    expect(apiTitle({ id: 'shopify', name: '' })).toBe('Shopify');
  });
});
