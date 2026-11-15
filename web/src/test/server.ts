import { setupServer } from 'msw/node';
import { createHandlers } from '@/mocks/handlers';

export const TEST_API_BASE = 'http://api.test';
export const server = setupServer(...createHandlers(TEST_API_BASE));
