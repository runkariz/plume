import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ApiProvider } from '@/api/context';
import type { PlumeApi } from '@/api/client';
import { routes } from './routes';
import { ThemeProvider } from './theme';

export function App({ client }: { client: PlumeApi }) {
  const router = createBrowserRouter(routes);
  return (
    <ThemeProvider>
      <ApiProvider client={client}>
        <RouterProvider router={router} />
      </ApiProvider>
    </ThemeProvider>
  );
}
