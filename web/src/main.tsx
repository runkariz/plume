import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createApiClient } from '@/api/client';
import { mocksEnabled } from '@/api/config';
import { App } from '@/app/App';
import { authStore } from '@/app/authStore';
import '@fontsource-variable/fraunces/opsz.css';
import '@fontsource-variable/fraunces/opsz-italic.css';
import '@fontsource-variable/instrument-sans';
import '@fontsource-variable/jetbrains-mono';
import '@/styles/index.css';

async function start() {
  if (mocksEnabled()) {
    const { worker } = await import('@/mocks/browser');
    await worker.start({ onUnhandledFrame: 'bypass', quiet: true });
  }
  const root = document.getElementById('root');
  if (!root) throw new Error('#root missing');
  createRoot(root).render(
    <StrictMode>
      <App client={createApiClient(undefined, { maintainerKey: authStore.getKey })} />
    </StrictMode>,
  );
}

void start();
