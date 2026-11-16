# Embedding models

**Decision (owner, 2026-11-16): Plume stays on `gemini-embedding-001`.**
`gemini-embedding-2` is supported as an opt-in (`PLUME_EMBED_MODEL=gemini-embedding-2`,
optionally `PLUME_EMBED_PROMPT=gemini`), measured below, and not used by default.

## Measured (2026-11-16)

Setup:

- the frozen packages: Shopify v12d, WooCommerce v12c, Mirakl;
- 768 dimensions; each build evaluated with its own model;
- `gemini-embedding-001` with the key on the project path at `europe-west3`;
- `gemini-embedding-2` with ADC at location `eu` (`aiplatform.eu.rep.googleapis.com`).

Scores are strict recall@5 / MRR / top-1, then lenient@5 / lenient@1 (lenient counts the
question's documentation page as a hit too).

| API (questions) | Model | R@5 | MRR | Top-1 | Lenient@5 | Lenient@1 |
|---|---|---|---|---|---|---|
| Shopify (120) | 001 | 0.842 | 0.527 | 0.350 | 0.917 | 0.625 |
| | 2, plain | 0.750 | 0.440 | 0.250 | 0.867 | 0.600 |
| | 2, prompt | 0.808 | 0.546 | 0.375 | 0.883 | 0.633 |
| WooCommerce (75) | 001 | 0.880 | 0.558 | 0.347 | 0.893 | 0.627 |
| | 2, plain | 0.867 | 0.542 | 0.360 | 0.920 | 0.640 |
| | 2, prompt | 0.853 | 0.568 | 0.400 | 0.867 | 0.640 |
| Mirakl (120) | 001 | 0.742 | 0.500 | 0.358 | 0.742 | 0.358 |
| | 2, plain | 0.650 | 0.476 | 0.375 | 0.650 | 0.375 |
| | 2, prompt | 0.717 | 0.510 | 0.392 | 0.717 | 0.392 |

Load time for the same chunks (WooCommerce 412, Shopify 1,022, Mirakl 1,748):

- 001: 104 / 233 / 413 s (one text per request);
- 2: 18 / 36 / 65–67 s (`:batchEmbedContents`, 100 per call).

Reading:

- Plain `-2` loses up to 9 points of recall@5.
- With the task in the text ("prompt") it ranks the first answer slightly better than 001
  (MRR, top-1) but puts slightly fewer right answers in the top 5 (−0.03 recall@5).
- The differences are 2 to 4 questions per API.

## What gemini-embedding-2 needs

- It is served only on the multi-region endpoints: location `eu`
  (`aiplatform.eu.rep.googleapis.com`) or `us`. It is not at `europe-west3` or `global`.
- It takes OAuth or ADC only; API keys get 401. On GKE that means Workload Identity with
  `roles/aiplatform.user`.
- It uses `:embedContent` / `:batchEmbedContents` (1–250 texts per call). `:predict` answers
  400.
- It ignores `task_type`. Google's format writes the task into the text (see
  [ai.google.dev/gemini-api/docs/embeddings](https://ai.google.dev/gemini-api/docs/embeddings)):
  - documents: `title: {title} | text: {content}`, with title `none` when absent;
  - queries: `task: search result | query: {query}`.

  `PLUME_EMBED_PROMPT=gemini` does this; builds then record the model as
  `gemini-embedding-2+prompt`.
- 768 dims come back normalised (the default is 3072).

## Switch recipe (if the decision changes)

1. Configure the API, MCP and loader processes:

   ```
   PLUME_EMBEDDER=vertex
   PLUME_EMBED_MODEL=gemini-embedding-2
   PLUME_EMBED_PROMPT=gemini
   PLUME_VERTEX_AUTH=adc
   PLUME_VERTEX_PROJECT=<project>
   PLUME_VERTEX_EMBED_LOCATION=eu
   ```

   The pods need Workload Identity; generation can keep its key settings.
2. Reload every API with that configuration: a model change gives new builds, since the model
   is part of a build's identity, and the vector cache is keyed by model, so nothing is reused.
3. Export the new builds and restore them on prod TOGETHER with the configuration change.
   Until both are in place, prod search refuses hybrid queries on builds of the other model
   with a clear error (and so does the eval gate) instead of returning wrong results.
4. Set an eval-gate floor that suits the new model, if needed (`PLUME_GATE_MIN_RECALL` /
   `PLUME_GATE_MIN_RECALL_BY_EMBEDDER`).
