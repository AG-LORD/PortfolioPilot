import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const AUTH_PAGES = new Set(["/login", "/register"]);

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
          // Cache-Control headers that stop a CDN from caching a response carrying auth cookies.
          Object.entries(headers ?? {}).forEach(([key, value]) => supabaseResponse.headers.set(key, value));
        },
      },
    },
  );

  // Do not run code between createServerClient and getUser: getUser refreshes an expired access token.
  const { data: { user } } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  let redirectTo: string | null = null;
  if (pathname.startsWith("/dashboard") && !user) redirectTo = "/login";
  if (AUTH_PAGES.has(pathname) && user) redirectTo = "/dashboard";

  if (redirectTo) {
    const url = request.nextUrl.clone();
    url.pathname = redirectTo;
    url.search = "";
    const redirect = NextResponse.redirect(url);
    // Carry any refreshed session cookies over, or the browser keeps the stale ones.
    supabaseResponse.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
    return redirect;
  }

  return supabaseResponse;
}
