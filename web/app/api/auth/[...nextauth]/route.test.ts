import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock the NextAuth handlers so no real auth stack (Mongo adapter, Resend)
// loads, and the rate limiter so tests control allow/deny per key.
const { authGet, authPost, allow } = vi.hoisted(() => ({
  authGet: vi.fn(async () => new Response("auth-get")),
  authPost: vi.fn(async () => new Response("auth-post")),
  allow: vi.fn<(key: string, limit: number, windowMs: number) => Promise<boolean>>(
    async () => true,
  ),
}));
vi.mock("@/auth", () => ({
  handlers: { GET: authGet, POST: authPost },
}));
vi.mock("@/lib/ratelimit", () => ({ allow }));

import { GET, POST } from "./route";

function signinRequest(email = "victim@example.com") {
  return new Request("http://localhost/api/auth/signin/resend", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "x-forwarded-for": "203.0.113.9",
    },
    body: `email=${encodeURIComponent(email)}`,
  });
}

function context(segments: string[]) {
  return { params: Promise.resolve({ nextauth: segments }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  allow.mockResolvedValue(true);
});

describe("POST /api/auth/signin", () => {
  it("blocks when the per-day email limit is exhausted even if the per-minute limit allows", async () => {
    allow.mockImplementation(async (key) => !key.startsWith("signin:email:day:"));

    const response = await POST(signinRequest() as never, context(["signin", "resend"]));

    expect(response.status).toBe(429);
    expect(authPost).not.toHaveBeenCalled();
  });

  it("blocks when the per-day IP limit is exhausted even if the per-minute limit allows", async () => {
    allow.mockImplementation(async (key) => !key.startsWith("signin:ip:day:"));

    const response = await POST(signinRequest() as never, context(["signin", "resend"]));

    expect(response.status).toBe(429);
    expect(authPost).not.toHaveBeenCalled();
  });

  it("checks both minute and day windows for IP and email, then passes through", async () => {
    const response = await POST(signinRequest() as never, context(["signin", "resend"]));

    expect(response.status).toBe(200);
    expect(authPost).toHaveBeenCalledOnce();

    const keys = allow.mock.calls.map(([key]) => key);
    expect(keys).toContain("signin:ip:203.0.113.9");
    expect(keys).toContain("signin:ip:day:203.0.113.9");
    expect(keys).toContain("signin:email:victim@example.com");
    expect(keys).toContain("signin:email:day:victim@example.com");
  });
});

describe("GET /api/auth/callback", () => {
  it("blocks callback token verification once the per-IP limit is exhausted", async () => {
    allow.mockImplementation(async (key) => !key.startsWith("callback:ip:"));

    const request = new Request(
      "http://localhost/api/auth/callback/resend?token=abc&email=victim@example.com",
      { headers: { "x-forwarded-for": "203.0.113.9" } },
    );
    const response = await GET(request as never, context(["callback", "resend"]));

    expect(response.status).toBe(429);
    expect(authGet).not.toHaveBeenCalled();
  });

  it("passes the callback through when under the limit", async () => {
    const request = new Request(
      "http://localhost/api/auth/callback/resend?token=abc&email=victim@example.com",
      { headers: { "x-forwarded-for": "203.0.113.9" } },
    );
    const response = await GET(request as never, context(["callback", "resend"]));

    expect(response.status).toBe(200);
    expect(authGet).toHaveBeenCalledOnce();
    const keys = allow.mock.calls.map(([key]) => key);
    expect(keys).toContain("callback:ip:203.0.113.9");
  });

  it("leaves non-callback GETs (session, csrf, providers) unthrottled", async () => {
    const request = new Request("http://localhost/api/auth/session", {
      headers: { "x-forwarded-for": "203.0.113.9" },
    });
    const response = await GET(request as never, context(["session"]));

    expect(response.status).toBe(200);
    expect(authGet).toHaveBeenCalledOnce();
    expect(allow).not.toHaveBeenCalled();
  });
});
