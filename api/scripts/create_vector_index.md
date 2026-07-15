# Creating the Atlas vector search index for `kb_chunks`

`app/kb.py`'s `_vector_search` runs a `$vectorSearch` aggregation stage
against the `kb_chunks` collection. That stage requires an Atlas Search
vector index named `kb_chunks_vector` to already exist — it cannot be
created through a normal `createIndex` call, and it does not exist on
mongomock (which is why tests monkeypatch `kb._vector_search` instead of
exercising this for real). This index must be created once per environment
(dev cluster, staging, prod) directly against Atlas.

## Index definition

- Name: `kb_chunks_vector`
- Collection: `kb_chunks` (database: `inboxpilot`)
- Vector field: `embedding` — 1536 dimensions (OpenAI `text-embedding-3-small`),
  similarity `cosine`
- Filter field: `workspaceId` — lets `$vectorSearch`'s `filter` clause scope
  results to one workspace without a post-filter

```json
{
  "name": "kb_chunks_vector",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "embedding",
        "numDimensions": 1536,
        "similarity": "cosine"
      },
      {
        "type": "filter",
        "path": "workspaceId"
      }
    ]
  }
}
```

## Creating it with the Atlas CLI

1. Save the JSON above to a file, e.g. `kb_chunks_vector_index.json`.
2. Run:

```bash
atlas clusters search indexes create \
  --clusterName <your-cluster-name> \
  --db inboxpilot \
  --collection kb_chunks \
  --file kb_chunks_vector_index.json
```

3. Confirm it's built (status `READY`, not `BUILDING`):

```bash
atlas clusters search indexes list \
  --clusterName <your-cluster-name> \
  --db inboxpilot \
  --collection kb_chunks
```

## Alternative: Atlas UI

Atlas → your cluster → **Search & Vector Search** tab → **Create Search
Index** → **JSON Editor** → select database `inboxpilot`, collection
`kb_chunks` → paste the `definition` object above (Atlas's UI already
scopes the name/collection/db, so only the `fields` array is needed there)
→ **Create Search Index**.

## Notes

- If `text-embedding-3-small` is ever swapped for a model with a different
  output size, `numDimensions` must be updated to match, and existing
  `kb_chunks.embedding` values must be re-embedded — a vector index cannot
  mix dimensionalities.
- Every workspace shares this one collection/index; the `workspaceId`
  filter field is what keeps `kb.retrieve` from leaking another
  workspace's chunks into a search.
