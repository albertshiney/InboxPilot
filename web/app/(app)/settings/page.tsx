import { auth } from "@/auth";
import SettingsClient from "@/components/settings/SettingsClient";

// The (app) layout is a server component and there's no SessionProvider
// mounted anywhere in the tree, so the simplest way to get the session's
// login email onto a client component is to read it here (server-side,
// `auth()` is cheap) and pass it down as a plain prop — no client-side
// session fetch/context needed for a single read-only field.
export default async function SettingsPage() {
  const session = await auth();
  const loginEmail = session?.user?.email ?? null;

  return <SettingsClient loginEmail={loginEmail} />;
}
