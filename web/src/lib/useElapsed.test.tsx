import { act, renderHook } from '@testing-library/react';
import { formatElapsed } from './format';
import { useElapsed } from './useElapsed';

describe('formatElapsed', () => {
  it('is a clock: m:ss, and h:mm:ss from an hour', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(9)).toBe('0:09');
    expect(formatElapsed(59.9)).toBe('0:59');
    expect(formatElapsed(161)).toBe('2:41');
    expect(formatElapsed(3600)).toBe('1:00:00');
    expect(formatElapsed(3725)).toBe('1:02:05');
    expect(formatElapsed(-4)).toBe('0:00');
  });
});

describe('useElapsed', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] }));
  afterEach(() => vi.useRealTimers());

  it('counts from when the page started watching, once a second, until it stops running', () => {
    const { result, rerender } = renderHook(({ running }) => useElapsed(running, null), {
      initialProps: { running: true },
    });
    expect(result.current).toBe(0);
    act(() => void vi.advanceTimersByTime(3000));
    expect(result.current).toBe(3);
    rerender({ running: false });
    act(() => void vi.advanceTimersByTime(5000));
    expect(result.current).toBe(3); // stopped: the interval is gone
  });

  it("follows the server's heartbeat: its seconds at the moment it arrived, then on from there", () => {
    const { result, rerender } = renderHook(
      ({ known }: { known: { seconds: number; at: number } | null }) => useElapsed(true, known),
      { initialProps: { known: null as { seconds: number; at: number } | null } },
    );
    act(() => void vi.advanceTimersByTime(2000));
    expect(result.current).toBe(2);
    // the server says the job has really run 161 s (it started before this page watched it)
    rerender({ known: { seconds: 161, at: Date.now() } });
    expect(result.current).toBe(161);
    act(() => void vi.advanceTimersByTime(4000));
    expect(result.current).toBe(165);
  });
});
