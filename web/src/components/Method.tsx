import type { HttpMethod } from '@/api/types';

export function MethodBadge({ method }: { method: HttpMethod }) {
  return <span className={`method ${method}`}>{method}</span>;
}
