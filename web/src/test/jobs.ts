import { authStore } from '@/app/authStore';
import type { JobStatus } from '@/api/types';
import { testClient } from './render';

/** Signs in and drives the (mock) backend to the wanted stage; returns the job id. */
export async function seedJob(stage: Exclude<JobStatus, 'failed' | 'published' | 'discarded'>) {
  authStore.signIn('pl_test', 'maintainer');
  const c = testClient();
  let job = await c.uploadPackage(
    new File(['zip'], 'shopify-package.zip', { type: 'application/zip' }),
  );
  if (stage === 'uploaded') return job.id;
  job = await c.reviewJob(job.id, {
    apiId: 'shopify',
    displayName: 'Shopify Admin REST',
    tag: '2026-11-14',
  });
  if (stage === 'reviewed') return job.id;
  await c.startBuild(job.id);
  if (stage === 'staged') await c.watchJob(job.id, () => undefined);
  return job.id;
}
