/**
 * Display names. The server gives what the package says: often the lowercase id ("woocommerce"), or a title-cased
 * id ("Woocommerce"). Brands with their own casing are fixed here until the server sends the vendor's display name.
 */
const BRANDS: Record<string, string> = {
  woocommerce: 'WooCommerce',
  bigcommerce: 'BigCommerce',
  github: 'GitHub',
  gitlab: 'GitLab',
  paypal: 'PayPal',
  hubspot: 'HubSpot',
  mailchimp: 'Mailchimp',
  openai: 'OpenAI',
  youtube: 'YouTube',
  linkedin: 'LinkedIn',
  quickbooks: 'QuickBooks',
};

function titleCase(id: string): string {
  const words = id.replace(/[-_]+/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : id;
}

/** The short label of an API ("WooCommerce"), from its id when the server only sent a lowercased or title-cased id. */
export function apiLabel(a: { id: string; shortName?: string }): string {
  const brand = BRANDS[a.id.toLowerCase()];
  if (brand) return brand;
  return a.shortName && a.shortName.trim() ? a.shortName : titleCase(a.id);
}

/** The full name of an API: keep the server's name unless it is just the id in lowercase. */
export function apiTitle(a: { id: string; name: string }): string {
  if (a.name.trim() !== '' && a.name.toLowerCase() !== a.id.toLowerCase()) return a.name;
  return BRANDS[a.id.toLowerCase()] ?? titleCase(a.id);
}
