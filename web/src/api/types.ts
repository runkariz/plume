/**
 * Hand-written types for the Plume HTTP API (W1 stub).
 * Replaced by types generated from the backend OpenAPI once plume-6f publishes it (P3).
 */
export type ApiStatus =
  { kind: 'ready'; recallAt5: number } | { kind: 'updating'; progress: number };

export interface ApiSummary {
  id: string;
  name: string;
  category: string;
  summary: string;
  endpoints: number;
  models: number;
  guides: number;
  docsAsOf: string; // ISO date
  status: ApiStatus;
  logo: { text: string; color: string };
}

export interface ApiList {
  items: ApiSummary[];
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
