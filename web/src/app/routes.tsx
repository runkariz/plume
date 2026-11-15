import type { RouteObject } from 'react-router-dom';
import { ComingSoon } from '@/pages/ComingSoon';
import { HomeStub } from '@/pages/HomeStub';
import { KitPage } from '@/pages/KitPage';
import { NotFound } from '@/pages/NotFound';
import { Layout } from './Layout';

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomeStub /> },
      { path: 'apis/:apiId', element: <ComingSoon title="API detail" /> },
      { path: 'maintainer', element: <ComingSoon title="Maintainer sign-in" /> },
      { path: 'models', element: <ComingSoon title="Models" /> },
      { path: 'kit', element: <KitPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];
