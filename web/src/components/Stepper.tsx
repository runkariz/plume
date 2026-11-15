import { CheckIcon } from '@/icons';

const STEPS = ['Upload', 'Review changes', 'Build', 'Publish'];

/** 1-based current step; steps before it are done. `allDone` marks every step done. */
export function Stepper({ current, allDone = false }: { current: number; allDone?: boolean }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const state = allDone || n < current ? 'done' : n === current ? 'on' : 'todo';
        return (
          <li
            key={label}
            className={`step ${state}`}
            aria-current={state === 'on' ? 'step' : undefined}
          >
            <i aria-hidden>{state === 'done' ? <CheckIcon width={14} height={14} /> : n}</i>
            <span>
              {label}
              {state === 'done' ? <span className="sr-only"> (done)</span> : null}
            </span>
            {i < STEPS.length - 1 ? (
              <span className={`bar${state === 'done' ? ' done' : ''}`} aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
