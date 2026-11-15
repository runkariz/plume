import { useIsMaintainer } from '@/app/authStore';
import { MaintainerHome } from './MaintainerHome';
import { SignInPage } from './SignInPage';

export function MaintainerEntry() {
  return useIsMaintainer() ? <MaintainerHome /> : <SignInPage />;
}
