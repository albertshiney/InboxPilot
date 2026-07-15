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

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: MongoDBAdapter(getMongoClient),
  providers: [
    Resend({
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
      const client = await getMongoClient();
      const db = client.db();
      const workspace = defaultWorkspace(user.id!);
      const { insertedId } = await db
        .collection("workspaces")
        .insertOne(workspace);

      await db
        .collection("users")
        .updateOne(
          { _id: new ObjectId(user.id) },
          { $set: { workspaceId: insertedId.toHexString() } },
        );
    },
  },
  callbacks: {
    async session({ session, user }) {
      if (session.user) {
        session.user.workspaceId = (user as { workspaceId?: string })
          .workspaceId as string;
      }
      return session;
    },
  },
});
