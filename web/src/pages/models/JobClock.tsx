import { formatElapsed } from '@/lib/format';
import { useElapsed } from '@/lib/useElapsed';

/** The latest heartbeat of a generation job: the server's elapsed seconds at `at` (our clock), and what it waits for. */
export interface Beat {
  seconds: number;
  at: number;
  round?: number;
  of?: number;
  phase?: string;
  detail?: string;
  /** The set member being written. */
  concept?: string;
}

const PHASES: Record<string, string> = {
  waiting_for_model: 'Waiting for the model',
  validating: 'Checking the draft',
  context: 'Reading the docs',
};

/** "Waiting for the model", from the server's phase (or its own detail); an unknown phase reads as plain words. */
export function beatText(beat: Beat): string {
  if (beat.detail) return beat.detail;
  if (beat.phase) return PHASES[beat.phase] ?? beat.phase.replace(/_/g, ' ');
  return 'Working';
}

/**
 * "Working on the server · 2:41": the badge of a running job. The clock ticks every second between the server's
 * heartbeats, so a long model call does not look frozen. Not a live region (it would announce every second).
 */
export function JobClock({ running, beat }: { running: boolean; beat: Beat | null }) {
  const seconds = useElapsed(running, beat ? { seconds: beat.seconds, at: beat.at } : null);
  return (
    <span className="live">
      <span className="dot" aria-hidden /> Working on the server ·{' '}
      <span className="mono">{formatElapsed(seconds)}</span>
    </span>
  );
}

/**
 * The server's own word on what it is doing ("Waiting for the model, 2:41 (round 2 of 3)"). It changes only when a
 * heartbeat arrives (every few seconds), so it is a polite live region.
 */
export function BeatLine({ beat, maxRounds }: { beat: Beat | null; maxRounds?: number }) {
  if (!beat) return null;
  return (
    <p role="status" className="small muted job-beat">
      {beatText(beat)}
      {beat.concept ? ` (${beat.concept})` : ''}, {formatElapsed(beat.seconds)}
      {beat.round && (beat.of ?? maxRounds)
        ? ` (round ${beat.round} of ${beat.of ?? maxRounds})`
        : ''}
    </p>
  );
}
