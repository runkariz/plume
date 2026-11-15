import { graphHeight, READABLE_MIN_ZOOM, readableZoom } from './MappingGraph';

describe('graph sizing', () => {
  it('uses a fixed window; a readable view of a big model pans inside it', () => {
    expect(graphHeight(false)).toBe(760);
    expect(graphHeight(true)).toBe(820);
  });
  it('opens big models at a readable zoom: fit the width, never below the minimum', () => {
    expect(readableZoom(1376)).toBeCloseTo(1376 / 1500, 5);
    expect(readableZoom(2400)).toBe(1);
    expect(readableZoom(1016)).toBe(READABLE_MIN_ZOOM);
    expect(readableZoom(300)).toBe(READABLE_MIN_ZOOM);
    // text 14 px at the minimum zoom is about 12 px
    expect(14 * READABLE_MIN_ZOOM).toBeGreaterThanOrEqual(11.9);
  });
});
