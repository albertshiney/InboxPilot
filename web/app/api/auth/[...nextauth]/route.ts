import type { NextRequest } from "next/server";
import { handlers } from "@/auth";
import { allow } from "@/lib/ratelimit";

// Per-window limits for the magic-link sign-in endpoint. The sign-in POST is
// the only NextAuth subroute that triggers an outbound email + user/workspace
// row creation. Each dimension gets two windows: a per-minute burst limit and
// a per-day cap — the minute window alone resets forever, so without the day
// cap an attacker rotating IPs could spam any victim's inbox (and our Resend
// quota / sending-domain reputation) at 3 emails/min indefinitely.
const IP_LIMIT = 5; // requests per minute per client IP
const IP_DAILY_LIMIT = 30; // requests per day per client IP
const EMAIL_LIMIT = 3; // requests per minute per target email
const EMAIL_DAILY_LIMIT = 15; // requests per day per target email
const WINDOW_MS = 60_000; // 1 minute
const DAY_MS = 86_400_000; // 24 hours

// The magic-link verification GET (`/api/auth/callback/resend?token=...`)
// consumes a token guess per request, so it gets a per-IP throttle too —
// otherwise the token could be brute-forced at unlimited speed. Generous
// enough for real logins (one callback hit per login); session/csrf/providers
// GETs stay unthrottled since normal operation polls them.
const CALLBACK_IP_LIMIT = 10; // requests per minute per client IP
const CALLBACK_IP_DAILY_LIMIT = 100; // requests per day per client IP

// Derive the client IP from the last hop of x-forwarded-for, falling back to
// other proxy headers. Never throws; returns "unknown" if nothing is present.
function clientIp(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) {
    const parts = xff.split(",").map((p) => p.trim()).filter(Boolean);
    if (parts.length > 0) {
      return parts[parts.length - 1];
    }
  }
  return (
    request.headers.get("x-real-ip") ??
    request.headers.get("cf-connecting-ip") ??
    "unknown"
  );
}

// Best-effort extraction of the target email from the sign-in POST body without
// consuming the request stream that NextAuth needs. We clone the request so the
// underlying handler still sees an intact body.
async function targetEmail(request: Request): Promise<string | null> {
  try {
    const contentType = request.headers.get("content-type") ?? "";
    const clone = request.clone();
    if (contentType.includes("application/x-www-form-urlencoded")) {
      const form = await clone.formData();
      const email = form.get("email");
      return typeof email === "string" ? email.trim().toLowerCase() : null;
    }
    if (contentType.includes("application/json")) {
      const body = (await clone.json()) as { email?: unknown };
      return typeof body.email === "string"
        ? body.email.trim().toLowerCase()
        : null;
    }
  } catch {
    // Malformed/absent body — nothing to key on.
  }
  return null;
}

const tooMany = () =>
  new Response(
    JSON.stringify({ error: "Too many requests. Please try again shortly." }),
    {
      status: 429,
      headers: {
        "content-type": "application/json",
        "retry-after": String(Math.ceil(WINDOW_MS / 1000)),
      },
    },
  );

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ nextauth: string[] }> },
): Promise<Response> {
  const { nextauth } = await context.params;
  const path = Array.isArray(nextauth) ? nextauth.join("/") : "";

  // Only throttle the sign-in path; every other NextAuth POST passes straight
  // through untouched.
  if (path.includes("signin")) {
    const ip = clientIp(request);
    if (
      !(await allow(`signin:ip:${ip}`, IP_LIMIT, WINDOW_MS)) ||
      !(await allow(`signin:ip:day:${ip}`, IP_DAILY_LIMIT, DAY_MS))
    ) {
      return tooMany();
    }

    const email = await targetEmail(request);
    if (
      email &&
      (!(await allow(`signin:email:${email}`, EMAIL_LIMIT, WINDOW_MS)) ||
        !(await allow(`signin:email:day:${email}`, EMAIL_DAILY_LIMIT, DAY_MS)))
    ) {
      return tooMany();
    }
  }

  return handlers.POST(request);
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ nextauth: string[] }> },
): Promise<Response> {
  const { nextauth } = await context.params;
  const path = Array.isArray(nextauth) ? nextauth.join("/") : "";

  // Only throttle the magic-link verification callback; every other NextAuth
  // GET (session, csrf, providers) passes straight through untouched.
  if (path.includes("callback")) {
    const ip = clientIp(request);
    if (
      !(await allow(`callback:ip:${ip}`, CALLBACK_IP_LIMIT, WINDOW_MS)) ||
      !(await allow(`callback:ip:day:${ip}`, CALLBACK_IP_DAILY_LIMIT, DAY_MS))
    ) {
      return tooMany();
    }
  }

  return handlers.GET(request);
}
