/**
 * "My models" in the mock server: a link per person (`c-...`), holding the lineages saved under it. The demo links
 * stand for the unlisted demo lineage and the demo unlisted set; the legacy owner keys of the seeds map to them
 * (the server's transition: `POST /v1/models/mine` answers the links the keys became).
 */
export const DEMO_COLLECTION = 'c-DemoCollection3f9a0c71d2e8';
export const SET_COLLECTION = 'c-SetCollection7d1b4a9e0c5f2a';

/** The old owner keys of the seeds, and the link each one became. */
export const LEGACY_KEYS: Record<string, string> = {
  'ok-demo-3f9a0c71d2e84b5f': DEMO_COLLECTION,
  pk_set_demo_owner_key: SET_COLLECTION,
};

export interface MockCollection {
  id: string;
  mergedInto?: string;
}

/** "/mine/<id>": the server answers a path when it does not know the web's public address. */
export const collectionUrl = (id: string) => `/mine/${id}`;
