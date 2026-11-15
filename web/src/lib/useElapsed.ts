import { useEffect, useState } from 'react';

/**
 * Seconds a job has been running, ticking once a second while `running`. The server's heartbeat says how long it
 * has really been (`known`: elapsed seconds at the moment it arrived); between heartbeats and before the first one
 * the clock keeps going from there (or from when the page started watching), so a long model call never looks frozen.
 */
export function useElapsed(
  running: boolean,
  known: { seconds: number; at: number } | null,
): number {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  const base = known ? known.seconds + (now - known.at) / 1000 : (now - start) / 1000;
  return Math.max(0, Math.floor(base));
}
