import { GOLD_LABEL } from './notes';

describe('gold labels', () => {
  it('names the top-1 score under its new and its old key', () => {
    expect(GOLD_LABEL.top1_rate).toBe('top-1 hit rate');
    // release notes made before the rename keep citation_hit_rate in their stored gold block
    expect(GOLD_LABEL.citation_hit_rate).toBe('top-1 hit rate');
  });
});
