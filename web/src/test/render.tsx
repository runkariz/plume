import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApiProvider } from '@/api/context';
import { createApiClient, type PlumeApi } from '@/api/client';
import { routes } from '@/app/routes';
import { ThemeProvider } from '@/app/theme';
import { TEST_API_BASE } from './server';

export function renderApp(path = '/', client: PlumeApi = createApiClient(TEST_API_BASE)) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <RouterProvider router={router} />
      </ApiProvider>
    </ThemeProvider>,
  );
}
