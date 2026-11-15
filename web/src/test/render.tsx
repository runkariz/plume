import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApiProvider } from '@/api/context';
import { createApiClient, type PlumeApi } from '@/api/client';
import { authStore } from '@/app/authStore';
import { routes } from '@/app/routes';
import { ThemeProvider } from '@/app/theme';
import { TEST_API_BASE } from './server';

export function testClient() {
  return createApiClient(TEST_API_BASE, { maintainerKey: authStore.getKey, retryDelayMs: () => 0 });
}

export function renderApp(path = '/', client: PlumeApi = testClient()) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <RouterProvider router={router} />
      </ApiProvider>
    </ThemeProvider>,
  );
}
