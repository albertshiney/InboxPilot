"""One-off migration: copy NextAuth/workspace docs from db `test` to db
`inboxpilot`.

Background: before the web app pinned its Mongo database name explicitly
(see `web/auth.ts` / `web/lib/mongodb.ts`), the NextAuth MongoDB adapter and
`ensureWorkspaceForUser` ran with no database name given to `client.db()`,
which the driver silently resolves to a database literally named `test`
(when `MONGODB_URI` carries no path segment, e.g. many Atlas SRV strings).
Meanwhile the FastAPI backend has always hard-coded `inboxpilot`
(`app/db.py`). So any local/staging deployment that logged in before this
fix has its users/sessions/workspaces sitting in `test`, invisible to the
backend.

This script copies the four collections NextAuth + workspace bootstrap
write to — `users`, `workspaces`, `sessions`, `verification_tokens` — from
`test` into `inboxpilot`, INSERTING ONLY DOCS THAT DON'T ALREADY EXIST
THERE (matched by `_id`). It never overwrites or deletes anything in
`inboxpilot`. This is intentionally conservative: existing `inboxpilot`
data (e.g. anything created directly against the pinned database already)
always wins over anything found in `test`.

This script is NOT wired into any application code path, CI job, or
startup hook. It must be run manually, once, by a human who has confirmed
the target environment actually has a stray `test` database to migrate
from:

    cd api && .venv/bin/python scripts/migrate_test_db.py

Reads `MONGODB_URI` from the environment (falls back to the same default as
`app.config.Settings.mongodb_uri`, `mongodb://localhost:27017`). Safe to
run multiple times (idempotent) since re-runs only ever insert docs whose
`_id` isn't already present in `inboxpilot`.
"""

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

COLLECTIONS = ["users", "workspaces", "sessions", "verification_tokens"]


async def migrate() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri)
    source_db = client["test"]
    target_db = client["inboxpilot"]

    for name in COLLECTIONS:
        source = source_db[name]
        target = target_db[name]

        existing_ids = {doc["_id"] async for doc in target.find({}, {"_id": 1})}

        to_insert = []
        async for doc in source.find({}):
            if doc["_id"] not in existing_ids:
                to_insert.append(doc)

        if to_insert:
            result = await target.insert_many(to_insert)
            inserted = len(result.inserted_ids)
        else:
            inserted = 0

        skipped = await source.count_documents({}) - inserted
        print(
            f"{name}: inserted {inserted} new doc(s) into inboxpilot "
            f"(skipped {skipped} already present)"
        )

    client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
