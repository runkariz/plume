import { useCallback, useState } from 'react';
import { useApiClient } from '@/api/context';
import type { Job, JobStatus } from '@/api/types';
import { useAsync } from '@/api/useAsync';

export type Step = 'upload' | 'review' | 'build' | 'publish';

/** Which wizard step a job belongs to; a page redirects when the job is somewhere else. */
export function stepFor(status: JobStatus): Step {
  switch (status) {
    case 'uploaded':
      return 'upload';
    case 'reviewed':
      return 'review';
    case 'building':
    case 'failed':
      return 'build';
    default:
      return 'publish';
  }
}

export function stepPath(job: Pick<Job, 'id' | 'apiId'>, step: Step): string {
  return step === 'upload'
    ? `/maintainer/apis/${job.apiId}/update`
    : `/maintainer/jobs/${job.id}/${step}`;
}

/** Loads a job and lets the page replace it with the response of an action. */
export function useJob(jobId: string) {
  const client = useApiClient();
  const load = useCallback((signal: AbortSignal) => client.getJob(jobId, signal), [client, jobId]);
  const { state, retry } = useAsync(load);
  // keyed by job id so a stale override never leaks into another job
  const [override, setOverride] = useState<Job | null>(null);
  const job =
    override && override.id === jobId ? override : state.status === 'ready' ? state.data : null;
  return { state, job, setJob: setOverride, retry };
}
