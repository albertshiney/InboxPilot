import { MongoClient } from "mongodb";

// Lazily-created MongoClient shared by the NextAuth MongoDB adapter. The
// adapter accepts a function that resolves to a connected client, and only
// calls it when a request actually needs the database — so importing this
// module (or `auth.ts`) must never require MONGODB_URI to be set or a live
// Mongo connection to exist, e.g. when just rendering /login or building.

declare global {
  var _mongoClientPromise: Promise<MongoClient> | undefined;
}

export default async function getMongoClient(): Promise<MongoClient> {
  if (!global._mongoClientPromise) {
    const uri = process.env.MONGODB_URI;
    if (!uri) {
      throw new Error("MONGODB_URI is not set");
    }
    global._mongoClientPromise = new MongoClient(uri).connect();
  }
  return global._mongoClientPromise;
}
