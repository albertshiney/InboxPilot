import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

// This route is the ONLY path from the browser to the FastAPI backend.
// It validates the NextAuth session, then forwards the request verbatim
// (method, query string, and JSON/multipart body) to
// `${BACKEND_URL}/<fastapi-path>`, stamping on the internal auth headers
// the backend expects. Every frontend call goes through `web/lib/api.ts`,
// which hits `/api/backend/<path>`.

export const runtime = "nodejs";

// Headers that must not be forwarded as-is: `host`/`content-length` describe
// this request to Next.js, not the backend, and `cookie` carries the
// browser's NextAuth session cookie, which the backend has no use for (and
// must never see). Everything else — including `content-type` — passes
// through untouched so JSON and multipart bodies keep working.
const STRIPPED_REQUEST_HEADERS = new Set(["host", "cookie", "content-length"]);

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const session = await auth();
  const workspaceId = session?.user?.workspaceId;

  if (!workspaceId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) {
    console.error("BACKEND_URL or INTERNAL_API_KEY is not configured");
    return NextResponse.json(
      { error: "Backend proxy misconfigured" },
      { status: 500 },
    );
  }

  const { path } = await params;

  // Reject path traversal attempts
  for (const segment of path) {
    if (segment === ".." || segment === ".") {
      return NextResponse.json({ error: "Invalid path" }, { status: 400 });
    }
  }

  // Pin every forwarded request to the backend origin. Percent-encode each
  // path segment so a segment cannot smuggle in a scheme (e.g. "https:") or
  // a "//" that would let `new URL` resolve to an attacker-controlled origin
  // — otherwise the secret `X-Internal-Key` header below could be sent off
  // to that origin (SSRF / key leak).
  const base = new URL(backendUrl);
  const safePath = path.map(encodeURIComponent).join("/");
  const targetUrl = new URL(safePath, `${base.origin}/`);
  if (targetUrl.origin !== base.origin) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  targetUrl.search = request.nextUrl.search;

  const forwardedHeaders = new Headers(request.headers);
  for (const name of STRIPPED_REQUEST_HEADERS) {
    forwardedHeaders.delete(name);
  }
  forwardedHeaders.set("X-Internal-Key", internalApiKey);
  forwardedHeaders.set("X-Workspace-Id", workspaceId);

  // GET/HEAD requests must not carry a body (fetch throws otherwise).
  const hasRequestBody = !["GET", "HEAD"].includes(request.method);

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: forwardedHeaders,
    body: hasRequestBody ? request.body : undefined,
    // Never follow backend redirects: a 3xx could bounce this key-bearing
    // request to an off-origin location, re-leaking `X-Internal-Key`.
    redirect: "manual",
  };
  if (hasRequestBody) {
    // Required by undici/fetch whenever a streaming (ReadableStream) body
    // is supplied, so both JSON and multipart request bodies stream through
    // without being buffered in memory.
    init.duplex = "half";
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(targetUrl, init);
  } catch (error) {
    console.error("Backend fetch failed:", error);
    return NextResponse.json(
      { error: "Backend unreachable" },
      { status: 502 },
    );
  }

  const responseHeaders: Record<string, string> = {};
  const contentType = backendResponse.headers.get("content-type");
  if (contentType) {
    responseHeaders["content-type"] = contentType;
  }

  return new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    headers: responseHeaders,
  });
}

export {
  handler as GET,
  handler as POST,
  handler as PATCH,
  handler as DELETE,
};
