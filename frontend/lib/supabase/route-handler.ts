import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Supabase client for OAuth Route Handlers.
 * Recreates the redirect response whenever auth cookies are set (required for PKCE).
 */
export function createOAuthCallbackClient(
  request: NextRequest,
  redirectUrl: string
): { supabase: ReturnType<typeof createServerClient>; getResponse: () => NextResponse } {
  let response = NextResponse.redirect(redirectUrl);

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            request.cookies.set(name, value)
          );
          response = NextResponse.redirect(redirectUrl);
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  return {
    supabase,
    getResponse: () => response,
  };
}

export function copyResponseCookies(
  source: NextResponse,
  destination: NextResponse
) {
  source.cookies.getAll().forEach(({ name, value, ...options }) => {
    destination.cookies.set(name, value, options);
  });
}
