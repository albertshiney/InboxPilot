import getMongoClient from "@/lib/mongodb";

// Mongo-backed fixed-window rate limiter. Designed for serverless where an
// in-memory counter would not persist across invocations. Each call maps to a
// window bucket keyed by `key` + the window's start timestamp, and atomically
// increments a counter for that bucket via an upsert. A TTL index on
// `expiresAt` lets Mongo reap old buckets automatically.

const COLLECTION = "rate_limits";

// A fixed-window bucket. `_id` is a string (`${key}:${windowStart}`) rather
// than an ObjectId so buckets are addressable without a lookup.
interface RateLimitDoc {
  _id: string;
  count: number;
  expiresAt: Date;
}

let ttlIndexPromise: Promise<unknown> | null = null;

async function getCollection() {
  const client = await getMongoClient();
  // Pinned to the same `inboxpilot` database as the rest of the app (see
  // auth.ts / lib/mongodb.ts for why the db name can't be left to the URI).
  const db = client.db("inboxpilot");
  const collection = db.collection<RateLimitDoc>(COLLECTION);

  // Ensure the TTL index exists exactly once per process. createIndex is
  // idempotent, and we cache the promise so concurrent callers share it.
  if (!ttlIndexPromise) {
    ttlIndexPromise = collection
      .createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 })
      .catch((err) => {
        // Reset so a later call can retry if index creation transiently failed.
        ttlIndexPromise = null;
        throw err;
      });
  }
  try {
    await ttlIndexPromise;
  } catch {
    // Never let index bookkeeping break the actual limiter call.
  }

  return collection;
}

/**
 * Returns true if the call is allowed under the limit, false if the limit for
 * the current window has been exceeded. Fails open (returns true) if the
 * datastore is unreachable so that a Mongo outage cannot lock everyone out.
 *
 * @param key      Unique identity for the thing being limited (e.g. `signin:ip:1.2.3.4`).
 * @param limit    Max number of allowed calls within the window.
 * @param windowMs Window length in milliseconds.
 */
export async function allow(
  key: string,
  limit: number,
  windowMs: number,
): Promise<boolean> {
  try {
    const now = Date.now();
    const windowStart = Math.floor(now / windowMs) * windowMs;
    const expiresAt = new Date(windowStart + windowMs);
    const bucketId = `${key}:${windowStart}`;

    const collection = await getCollection();

    // Atomic upsert-and-increment. Concurrent calls for the same bucket race
    // on a single document; $inc is atomic server-side, so each returns a
    // distinct post-increment count.
    const result = await collection.findOneAndUpdate(
      { _id: bucketId },
      {
        $inc: { count: 1 },
        $setOnInsert: { expiresAt },
      },
      { upsert: true, returnDocument: "after" },
    );

    const count = result?.count ?? 1;
    return count <= limit;
  } catch {
    // Fail open: do not block legitimate auth traffic on limiter failure.
    return true;
  }
}
