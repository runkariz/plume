import { createContext, useContext, type ReactNode } from 'react';
import type { PlumeApi } from './client';

const ApiContext = createContext<PlumeApi | null>(null);

export function ApiProvider({ client, children }: { client: PlumeApi; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export function useApiClient(): PlumeApi {
  const c = useContext(ApiContext);
  if (!c) throw new Error('useApiClient must be used inside ApiProvider');
  return c;
}
