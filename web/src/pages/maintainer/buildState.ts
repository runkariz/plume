import type { EventSource, JobEvent, StepKey, StepStatus } from '@/api/types';
import { STEP_KEYS } from '@/api/types';

export interface LogLine {
  id: string;
  t: string;
  source: EventSource;
  message: string;
}

export interface BuildState {
  phase: 'connecting' | 'live' | 'staged' | 'failed' | 'lost';
  steps: Record<StepKey, { status: StepStatus; detail: string }>;
  progress: { done: number; total: number; etaSeconds: number | null } | null;
  logs: LogLine[];
  services: { postgres: string | null; gemini: string | null };
  message: string | null;
}

export const STEP_TITLES: Record<StepKey, string> = {
  validate: 'Validate',
  chunk: 'Chunk',
  diff: 'Diff',
  embed: 'Embed with Gemini',
  store: 'Store in Postgres',
  evaluate: 'Evaluate',
};

export const STEP_IDLE: Record<StepKey, string> = {
  validate: 'Check the package',
  chunk: 'Split the documents into chunks',
  diff: 'Compare with the live build',
  embed: 'Waiting for the diff',
  store: 'Staged, waiting for embeddings',
  evaluate: 'Gold questions, answer checks',
};

const MAX_LOG = 400;

export function initialBuildState(): BuildState {
  const steps = Object.fromEntries(
    STEP_KEYS.map((k) => [k, { status: 'pending' as StepStatus, detail: STEP_IDLE[k] }]),
  ) as BuildState['steps'];
  return {
    phase: 'connecting',
    steps,
    progress: null,
    logs: [],
    services: { postgres: null, gemini: null },
    message: null,
  };
}

export type BuildAction = JobEvent | { type: 'reset' } | { type: 'lost'; message: string };

export function buildReducer(state: BuildState, a: BuildAction): BuildState {
  switch (a.type) {
    case 'reset':
      return initialBuildState();
    case 'lost':
      return { ...state, phase: 'lost', message: a.message };
    case 'log': {
      // events are replayed after a reconnect: ignore a line we already have
      if (state.logs.some((l) => l.id === a.id)) return state;
      const logs = [...state.logs, { id: a.id, t: a.t, source: a.source, message: a.message }];
      return { ...state, phase: 'live', logs: logs.slice(-MAX_LOG) };
    }
    case 'step':
      return {
        ...state,
        phase: 'live',
        steps: { ...state.steps, [a.key]: { status: a.status, detail: a.detail } },
      };
    case 'progress':
      return {
        ...state,
        phase: 'live',
        progress: { done: a.done, total: a.total, etaSeconds: a.etaSeconds },
      };
    case 'service':
      return { ...state, services: { ...state.services, [a.service]: a.detail } };
    case 'done':
      return { ...state, phase: a.status, message: a.message ?? null };
  }
}
