import NextAuth from "next-auth";
import Resend from "next-auth/providers/resend";
import { MongoDBAdapter } from "@auth/mongodb-adapter";
import { ObjectId } from "mongodb";
import getMongoClient from "@/lib/mongodb";

// Default settings copied onto every newly-created workspace. The FastAPI
// backend reads these exact field names — do not rename without updating it.
function defaultWorkspace(ownerId: string) {
  return {
    name: "My workspace",
    ownerId,
    settings: {
      autopilot: false,
      confidenceThreshold: 85,
      tone: "friendly",
      signature: "",
      blockedCategories: ["refund"],
      customInstructions: "",
    },
    plan: null,
    subscriptionStatus: "none",
    stripeCustomerId: null,
    trialEndsAt: null,
    usage: {
      emailsProcessedThisMonth: 0,
    },
    createdAt: new Date(),
  };
}

// Ensures the given user has a workspace, self-healing the case where a
// previous bootstrap attempt inserted the workspace but failed before
// stamping the id back onto the user doc (or two concurrent logins raced
// each other). Always returns a workspaceId string; never creates a
// duplicate workspace for the same owner.
async function ensureWorkspaceForUser(userId: string): Promise<string> {
  const client = await getMongoClient();
  // Pinned explicitly — `MONGODB_URI` commonly carries no path segment
  // (e.g. an Atlas SRV string without `/inboxpilot`), in which case the
  // driver's `client.db()` silently defaults to a database named `test`.
  // The FastAPI backend always reads/writes `inboxpilot` (see
  // `api/app/db.py`), so this must match or logins/workspaces split across
  // two different databases.
  const db = client.db("inboxpilot");

  const existingUser = await db
    .collection("users")
    .findOne<{ workspaceId?: string }>({ _id: new ObjectId(userId) });

  if (existingUser?.workspaceId) {
    return existingUser.workspaceId;
  }

  const existingWorkspace = await db
    .collection("workspaces")
    .findOne<{ _id: ObjectId }>({ ownerId: userId });

  const workspaceId = existingWorkspace
    ? existingWorkspace._id
    : (
        await db
          .collection("workspaces")
          .insertOne(defaultWorkspace(userId))
      ).insertedId;

  await db
    .collection("users")
    .updateOne(
      { _id: new ObjectId(userId) },
      { $set: { workspaceId: workspaceId.toHexString() } },
    );

  return workspaceId.toHexString();
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Pinned to the same `inboxpilot` database as `ensureWorkspaceForUser`
  // (and the FastAPI backend) — see the comment there for why this can't
  // be left to `MONGODB_URI`'s (possibly absent) path segment.
  adapter: MongoDBAdapter(getMongoClient, { databaseName: "inboxpilot" }),
  providers: [
    Resend({
      apiKey: process.env.RESEND_API_KEY,
      from: process.env.EMAIL_FROM,
    }),
  ],
  session: {
    strategy: "database",
  },
  pages: {
    signIn: "/login",
  },
  events: {
    async createUser({ user }) {
      // Bootstrap a workspace for every brand-new user and stamp its id back
      // onto the user document so session callbacks can read it.
      await ensureWorkspaceForUser(user.id!);
    },
  },
  callbacks: {
    async session({ session, user }) {
      const typedUser = user as { workspaceId?: string; id: string };
      const workspaceId =
        typedUser.workspaceId ?? (await ensureWorkspaceForUser(typedUser.id));
      if (session.user) {
        session.user.workspaceId = workspaceId;
      }
      return session;
    },
  },
});
