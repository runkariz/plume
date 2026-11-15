import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useIsMaintainer } from '@/app/authStore';

/** Maintainer pages need a key in memory; otherwise go to sign-in and come back afterwards. */
export function RequireMaintainer() {
  const signedIn = useIsMaintainer();
  const location = useLocation();
  if (!signedIn) return <Navigate to="/maintainer" replace state={{ next: location.pathname }} />;
  return <Outlet />;
}
