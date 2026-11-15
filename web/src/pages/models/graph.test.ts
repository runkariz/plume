import { inventorySnapshot } from '@/mocks/modelData';
import { buildGraph, canonNodeId, defaultSelection, NODE } from './graph';

describe('buildGraph', () => {
  const { nodes, edges } = buildGraph(inventorySnapshot);
  const byId = new Map(nodes.map((n) => [n.id, n]));

  it('creates one canonical node per field and one group per API', () => {
    expect(nodes.filter((n) => n.type === 'canonical')).toHaveLength(7);
    expect(nodes.filter((n) => n.type === 'apiGroup').map((n) => n.id)).toEqual([
      'group:shopify',
      'group:woocommerce',
      'group:mirakl',
    ]);
  });

  it('creates a field node for every distinct source path', () => {
    const apiFields = nodes.filter((n) => n.type === 'apiField');
    expect(apiFields).toHaveLength(5 + 5 + 4); // mapped fields per API, as in the coverage card
    expect(byId.has('api:shopify:variants[].sku')).toBe(true);
    expect(byId.has('api:mirakl:leadtime_to_ship')).toBe(true);
  });

  it('draws no edge for unsupported fields', () => {
    expect(edges.some((e) => e.data?.field === 'location_id' && e.data.apiId === 'mirakl')).toBe(
      false,
    );
    expect(edges.filter((e) => e.data?.field === 'location_id')).toHaveLength(1);
    expect(edges).toHaveLength(14);
  });

  it('marks derived edges as dashed with the transform label', () => {
    const e = edges.find((x) => x.data?.field === 'manage_stock' && x.data.apiId === 'shopify');
    expect(e?.label).toBe('not null = true');
    expect(e?.style?.strokeDasharray).toBeTruthy();
    const direct = edges.find((x) => x.data?.field === 'sku' && x.data.apiId === 'woocommerce');
    expect(direct?.label).toBeUndefined();
    expect(direct?.style?.strokeDasharray).toBeUndefined();
  });

  it('points edges from the left API into the canonical field and out to the right APIs', () => {
    const left = edges.find((x) => x.data?.apiId === 'shopify' && x.data.field === 'sku');
    expect(left?.target).toBe(canonNodeId('sku'));
    const right = edges.find((x) => x.data?.apiId === 'mirakl' && x.data.field === 'sku');
    expect(right?.source).toBe(canonNodeId('sku'));
  });

  it('keeps nodes inside each column and never overlaps field boxes', () => {
    const cols = new Map<number, { y: number }[]>();
    for (const n of nodes.filter((x) => x.type === 'apiField' || x.type === 'canonical')) {
      const list = cols.get(n.position.x) ?? [];
      list.push({ y: n.position.y });
      cols.set(n.position.x, list);
    }
    for (const list of cols.values()) {
      const ys = list.map((l) => l.y).sort((a, b) => a - b);
      ys.slice(1).forEach((y, i) => expect(y - (ys[i] ?? 0)).toBeGreaterThanOrEqual(NODE.fieldH));
    }
  });

  it('places the right-hand groups below each other', () => {
    const woo = byId.get('group:woocommerce');
    const mirakl = byId.get('group:mirakl');
    expect(mirakl?.position.y ?? 0).toBeGreaterThanOrEqual(
      (woo?.position.y ?? 0) + (woo?.height ?? 0),
    );
  });
});

describe('defaultSelection', () => {
  it('opens on the first derived mapping', () => {
    expect(defaultSelection(inventorySnapshot)).toEqual({
      field: 'quantity_available',
      apiId: 'shopify',
    });
  });
  it('falls back to the first direct mapping, or null when there are none', () => {
    const direct = { ...inventorySnapshot, fields: inventorySnapshot.fields.slice(0, 1) };
    expect(defaultSelection(direct)).toEqual({ field: 'sku', apiId: 'shopify' });
    expect(defaultSelection({ ...inventorySnapshot, fields: [] })).toBeNull();
  });
});
