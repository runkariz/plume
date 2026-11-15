import { EmptyState } from '@/components';

export function ComingSoon({ title }: { title: string }) {
  return <EmptyState title={title}>This page arrives in a later slice.</EmptyState>;
}
