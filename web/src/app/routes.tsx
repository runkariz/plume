import type { RouteObject } from 'react-router-dom';
import { ApiDetailPage } from '@/pages/ApiDetailPage';
import { DocumentPage } from '@/pages/DocumentPage';
import { AuthSchemePage } from '@/pages/sections/AuthSchemePage';
import { TriggerPage } from '@/pages/sections/TriggerPage';
import { Home } from '@/pages/Home';
import { KitPage } from '@/pages/KitPage';
import { NotFound } from '@/pages/NotFound';
import { TryItPage } from '@/pages/TryItPage';
import { PickApps } from '@/pages/models/PickApps';
import { Suggestions } from '@/pages/models/Suggestions';
import { CollectionPage } from '@/pages/mine/CollectionPage';
import { RelatedConcepts } from '@/pages/sets/RelatedConcepts';
import { BuildStep } from '@/pages/maintainer/BuildStep';
import { RequireMaintainer } from '@/pages/maintainer/Guard';
import { MaintainerEntry } from '@/pages/maintainer/MaintainerEntry';
import { PublishStep } from '@/pages/maintainer/PublishStep';
import { BuildsPage } from '@/pages/maintainer/release/BuildsPage';
import { ReleaseReview } from '@/pages/maintainer/release/ReleaseReview';
import { MappingReportPage } from '@/pages/maintainer/reports/MappingReportPage';
import { MappingReportsPage } from '@/pages/maintainer/reports/MappingReportsPage';
import { ReportPage } from '@/pages/maintainer/reports/ReportPage';
import { ReportsPage } from '@/pages/maintainer/reports/ReportsPage';
import { ReviewStep } from '@/pages/maintainer/ReviewStep';
import { UploadStep } from '@/pages/maintainer/UploadStep';
import { Layout } from './Layout';
import { RootError, RouteError } from './RouteError';

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    errorElement: <RootError />,
    children: [
      {
        // a page that crashes or fails to load shows the error page inside the layout (header kept)
        errorElement: <RouteError />,
        children: [
          { index: true, element: <Home /> },
          { path: 'apis/:apiId', element: <ApiDetailPage /> },
          { path: 'apis/:apiId/try', element: <TryItPage /> },
          { path: 'apis/:apiId/documents/:docId', element: <DocumentPage /> },
          { path: 'apis/:apiId/auth/:schemeId', element: <AuthSchemePage /> },
          { path: 'apis/:apiId/triggers/:triggerKey', element: <TriggerPage /> },
          { path: 'maintainer', element: <MaintainerEntry /> },
          {
            element: <RequireMaintainer />,
            children: [
              { path: 'maintainer/apis/:apiId/update', element: <UploadStep /> },
              { path: 'maintainer/jobs/:jobId/review', element: <ReviewStep /> },
              { path: 'maintainer/jobs/:jobId/build', element: <BuildStep /> },
              { path: 'maintainer/jobs/:jobId/publish', element: <PublishStep /> },
              { path: 'maintainer/reports', element: <ReportsPage /> },
              { path: 'maintainer/reports/:reportId', element: <ReportPage /> },
              { path: 'maintainer/mapping-reports', element: <MappingReportsPage /> },
              { path: 'maintainer/mapping-reports/:reportId', element: <MappingReportPage /> },
              { path: 'maintainer/apis/:apiId/builds', element: <BuildsPage /> },
              {
                path: 'maintainer/apis/:apiId/builds/:buildId/notes',
                element: <ReleaseReview />,
              },
            ],
          },
          { path: 'models', element: <PickApps /> },
          { path: 'models/suggest', element: <Suggestions /> },
          { path: 'models/related', element: <RelatedConcepts /> },
          { path: 'mine/:collectionId', element: <CollectionPage /> },
          {
            path: 'models/:snapshotId',
            // React Flow is large: load it only when a model is opened
            lazy: async () => ({ Component: (await import('@/pages/models/ModelView')).ModelView }),
            handle: { wide: true },
          },
          {
            path: 'model-sets/:setId',
            // React Flow is large: load it only when a model set is opened
            lazy: async () => ({
              Component: (await import('@/pages/sets/ModelSetView')).ModelSetView,
            }),
            handle: { wide: true },
          },
          { path: 'kit', element: <KitPage /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];
