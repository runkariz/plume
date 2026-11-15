import type { RouteObject } from 'react-router-dom';
import { ComingSoon } from '@/pages/ComingSoon';
import { ApiDetailPage } from '@/pages/ApiDetailPage';
import { Home } from '@/pages/Home';
import { KitPage } from '@/pages/KitPage';
import { NotFound } from '@/pages/NotFound';
import { TryItPage } from '@/pages/TryItPage';
import { Layout } from './Layout';

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'apis/:apiId', element: <ApiDetailPage /> },
      { path: 'apis/:apiId/try', element: <TryItPage /> },
      { path: 'maintainer', element: <ComingSoon title="Maintainer sign-in" /> },
      { path: 'models', element: <ComingSoon title="Models" /> },
      { path: 'kit', element: <KitPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];
