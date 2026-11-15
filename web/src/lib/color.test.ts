import { contrastRatio, luminance, readableOn } from './color';

describe('color helpers', () => {
  it('computes WCAG luminance and contrast', () => {
    expect(luminance('#000')).toBe(0);
    expect(luminance('#ffffff')).toBeCloseTo(1, 5);
    expect(luminance('nope')).toBeNull();
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0);
  });
  it('picks the readable text colour for data-driven backgrounds', () => {
    expect(readableOn('#d97706')).toBe('#1c1b1a'); // amber: dark text passes, white does not
    expect(readableOn('#5a8f2e')).toBe('#1c1b1a');
    expect(readableOn('#24292f')).toBe('#ffffff');
    expect(readableOn('#635bff')).toBe('#ffffff');
    expect(readableOn('rebeccapurple')).toBe('#ffffff'); // unknown formats fall back to white
  });
  it('never picks the worse of the two text colours', () => {
    for (const bg of [
      '#d97706',
      '#db2777',
      '#5b5bd6',
      '#2a6edb',
      '#7f54b3',
      '#f22f46',
      '#777777',
    ]) {
      const chosen = contrastRatio(readableOn(bg), bg) ?? 0;
      const other = contrastRatio(readableOn(bg) === '#ffffff' ? '#1c1b1a' : '#ffffff', bg) ?? 0;
      expect(chosen).toBeGreaterThanOrEqual(other);
      expect(chosen).toBeGreaterThanOrEqual(3.5); // mid-tone brand colours cannot always reach 4.5 with either colour
    }
  });
});

describe('data that is not a colour', () => {
  it('never throws: a missing colour is just "no luminance", and text on it is white', () => {
    expect(luminance(undefined as unknown as string)).toBeNull();
    expect(luminance(null as unknown as string)).toBeNull();
    expect(readableOn(undefined as unknown as string)).toBe('#ffffff');
    expect(contrastRatio('#fff', undefined as unknown as string)).toBeNull();
  });
});
