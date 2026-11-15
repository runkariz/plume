import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer';
import { FormData as NodeFormData } from 'undici';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { authStore } from '@/app/authStore';
import { server } from './server';

// jsdom's FormData cannot be serialized by Node's fetch (which MSW intercepts): use Node's own.
class TestFormData extends NodeFormData {
  // jsdom Files (from <input type=file> and `new File`) are not Node Blobs: re-wrap them, keeping name and type.
  override append(name: string, value: unknown, filename?: string) {
    if (typeof value === 'object' && value !== null && !(value instanceof NodeBlob)) {
      const f = value as { name?: string; type?: string; size?: number };
      return super.append(
        name,
        new NodeFile([`stub:${f.size ?? 0}`], filename ?? f.name ?? 'file', { type: f.type ?? '' }),
      );
    }
    return super.append(name, value as string, filename);
  }
}
globalThis.FormData = TestFormData as unknown as typeof FormData;

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterEach(() => {
  cleanup();
  authStore.signOut();
  server.resetHandlers();
});
afterAll(() => server.close());
