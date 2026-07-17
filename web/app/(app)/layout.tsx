import { redirect } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import MobileNav from "@/components/MobileNav";
import { auth } from "@/auth";

// Server-side access gate: every route under (app) requires an active Gmail
// connection AND an active/trialing subscription. One GET /settings covers
// both — it returns the connection doc and self-heals `subscriptionStatus`
// from Stripe when a checkout webhook was missed, so users landing back from
// Stripe checkout pass the gate even before the webhook arrives. Calls the
// FastAPI backend directly (same internal auth headers the `/api/backend`
// proxy stamps on) rather than going through the browser-facing proxy, since
// server components don't have a request origin to route relative fetches
// through.

const ACTIVE_SUBSCRIPTION_STATUSES = new Set(["active", "trialing"]);

type AccessGate = { connected: boolean; subscribed: boolean };

// Fail open — misconfiguration or backend downtime shouldn't lock users out.
const FAIL_OPEN: AccessGate = { connected: true, subscribed: true };

async function fetchAccessGate(workspaceId: string): Promise<AccessGate> {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) {
    console.error("BACKEND_URL or INTERNAL_API_KEY is not configured");
    return FAIL_OPEN;
  }

  try {
    const res = await fetch(new URL("settings", `${backendUrl}/`), {
      headers: {
        "X-Internal-Key": internalApiKey,
        "X-Workspace-Id": workspaceId,
      },
      cache: "no-store",
    });
    if (!res.ok) return FAIL_OPEN;
    const data = (await res.json()) as {
      connection?: { status?: string } | null;
      subscriptionStatus?: string;
    };
    return {
      connected: data.connection?.status === "active",
      subscribed: ACTIVE_SUBSCRIPTION_STATUSES.has(data.subscriptionStatus ?? "none"),
    };
  } catch (error) {
    console.error("Failed to check workspace access:", error);
    return FAIL_OPEN;
  }
}

export default async function AppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await auth();

  // Defense in depth: re-verify the session server-side on every (app) route
  // before the Gmail-connection gate runs. Unauthenticated requests go to login.
  if (!session?.user) {
    redirect("/login");
  }

  const workspaceId = session.user.workspaceId;

  if (workspaceId) {
    const gate = await fetchAccessGate(workspaceId);
    if (!gate.connected) {
      redirect("/onboarding");
    }
    if (!gate.subscribed) {
      redirect("/start-trial");
    }
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <Sidebar />
      <MobileNav />
      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-10">
          {children}
        </div>
      </main>
    </div>
  );
}
