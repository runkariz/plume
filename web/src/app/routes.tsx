import type { RouteObject } from 'react-router-dom';
import { ApiDetailPage } from '@/pages/ApiDetailPage';
import { Home } from '@/pages/Home';
import { KitPage } from '@/pages/KitPage';
import { NotFound } from '@/pages/NotFound';
import { TryItPage } from '@/pages/TryItPage';
import { PickApps } from '@/pages/models/PickApps';
import { Suggestions } from '@/pages/models/Suggestions';
import { BuildStep } from '@/pages/maintainer/BuildStep';
import { RequireMaintainer } from '@/pages/maintainer/Guard';
import { MaintainerEntry } from '@/pages/maintainer/MaintainerEntry';
import { PublishStep } from '@/pages/maintainer/PublishStep';
import { ReviewStep } from '@/pages/maintainer/ReviewStep';
import { UploadStep } from '@/pages/maintainer/UploadStep';
import { Layout } from './Layout';

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'apis/:apiId', element: <ApiDetailPage /> },
      { path: 'apis/:apiId/try', element: <TryItPage /> },
      { path: 'maintainer', element: <MaintainerEntry /> },
      {
        element: <RequireMaintainer />,
        children: [
          { path: 'maintainer/apis/:apiId/update', element: <UploadStep /> },
          { path: 'maintainer/jobs/:jobId/review', element: <ReviewStep /> },
          { path: 'maintainer/jobs/:jobId/build', element: <BuildStep /> },
          { path: 'maintainer/jobs/:jobId/publish', element: <PublishStep /> },
        ],
      },
      { path: 'models', element: <PickApps /> },
      { path: 'models/suggest', element: <Suggestions /> },
      {
        path: 'models/:snapshotId',
        // React Flow is large: load it only when a model is opened
        lazy: async () => ({ Component: (await import('@/pages/models/ModelView')).ModelView }),
        handle: { wide: true },
      },
      { path: 'kit', element: <KitPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];
