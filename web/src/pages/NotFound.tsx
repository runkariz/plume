import { Link } from 'react-router-dom';
import { EmptyState } from '@/components';

export function NotFound() {
  return (
    <EmptyState title="Page not found">
      <Link to="/">Back to the home page</Link>
    </EmptyState>
  );
}
