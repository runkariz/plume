import { filterOptions, picksFromNote, withPick } from './checkPicks';

const NOTE =
  'ambiguous: 156 operations share POST /sync; pass method=<name> in params or query (e.g. method=ae.merchant.assortment.seller.arrangement.plan.list, method=ae.merchant.assortment.seller.plan.chance.download, method=aliexpress.affiliate.category.get)';

describe('picksFromNote', () => {
  it('reads the examples at the end of the server note, in order', () => {
    expect(picksFromNote(NOTE)).toEqual([
      { key: 'method', value: 'ae.merchant.assortment.seller.arrangement.plan.list' },
      { key: 'method', value: 'ae.merchant.assortment.seller.plan.chance.download' },
      { key: 'method', value: 'aliexpress.affiliate.category.get' },
    ]);
  });
  it('gives nothing when the note has no examples, and drops repeats and cuts at the limit', () => {
    expect(picksFromNote('ambiguous: pass method=<name>')).toEqual([]);
    expect(picksFromNote(null)).toEqual([]);
    expect(picksFromNote('x (e.g. a=1, a=1, b=2, c=3)', 2)).toEqual([
      { key: 'a', value: '1' },
      { key: 'b', value: '2' },
    ]);
    expect(picksFromNote('x (e.g. method=<name>, nonsense, k=v)')).toEqual([
      { key: 'k', value: 'v' },
    ]);
  });
});

describe('withPick', () => {
  it('adds the pick and replaces an earlier value of the same key', () => {
    expect(withPick('limit, page_info', { key: 'method', value: 'a.b' })).toBe(
      'limit, page_info, method=a.b',
    );
    expect(withPick('method=old, limit', { key: 'method', value: 'a.b' })).toBe(
      'limit, method=a.b',
    );
    expect(withPick('', { key: 'method', value: 'a.b' })).toBe('method=a.b');
  });
});

describe('filterOptions', () => {
  const options = [{ value: 'ae.plan.list' }, { value: 'aliexpress.Category.get' }, { value: 'x' }];
  it('keeps the options that contain the text, whatever its case, and all of them for an empty filter', () => {
    expect(filterOptions(options, '')).toHaveLength(3);
    expect(filterOptions(options, '  ')).toHaveLength(3);
    expect(filterOptions(options, 'CATEGORY').map((o) => o.value)).toEqual([
      'aliexpress.Category.get',
    ]);
    expect(filterOptions(options, 'nope')).toEqual([]);
  });
});
