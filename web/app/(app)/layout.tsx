import { redirect } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import MobileNav from "@/components/MobileNav";
import { auth } from "@/auth";

// Server-side onboarding gate: every route under (app) requires an active
// Gmail connection. This calls the FastAPI backend directly (same internal
// auth headers the `/api/backend` proxy stamps on) rather than going through
// the browser-facing proxy, since server components don't have a request
// origin to route relative fetches through.
async function hasActiveGmailConnection(workspaceId: string): Promise<boolean> {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) {
    console.error("BACKEND_URL or INTERNAL_API_KEY is not configured");
    return true; // fail open — misconfiguration shouldn't lock users out
  }

  try {
    const res = await fetch(new URL("composio/status", `${backendUrl}/`), {
      headers: {
        "X-Internal-Key": internalApiKey,
        "X-Workspace-Id": workspaceId,
      },
      cache: "no-store",
    });
    if (!res.ok) return true;
    const data = (await res.json()) as { status?: string };
    return data.status === "active";
  } catch (error) {
    console.error("Failed to check Gmail connection status:", error);
    return true;
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
    const connected = await hasActiveGmailConnection(workspaceId);
    if (!connected) {
      redirect("/onboarding");
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
