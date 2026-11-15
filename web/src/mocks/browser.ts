import { setupWorker } from 'msw/browser';
import { createHandlers } from './handlers';

export const worker = setupWorker(...createHandlers(undefined, { eventDelayMs: 150 }));
