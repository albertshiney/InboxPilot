import { NextResponse } from "next/server";
import { auth } from "@/auth";

// Next.js 16 renamed the `middleware` file convention to `proxy` (see
// node_modules/next/dist/docs/.../file-conventions/proxy.md). Proxy defaults
// to the Node.js runtime, which the mongodb-backed database session strategy
// needs, so no explicit runtime export is required here.
export default auth((req) => {
  if (!req.auth) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/dashboard", "/inbox/:path*", "/knowledge", "/settings", "/onboarding"],
};
