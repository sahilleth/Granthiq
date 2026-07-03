import { authLogger } from "@/lib/auth-logger";
import { validateRedirectPath } from "@/lib/validate-redirect";
import { createOAuthCallbackClient } from "@/lib/supabase/route-handler";
import { NextResponse, type NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = validateRedirectPath(searchParams.get("next"));
  const errorParam = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  authLogger.logOAuthCallbackReceived("google");

  if (errorParam) {
    authLogger.logOAuthFailed("google", errorDescription ?? errorParam);
    return NextResponse.redirect(
      `${origin}/auth/login?error=${encodeURIComponent(errorDescription ?? errorParam)}`
    );
  }

  if (!code) {
    authLogger.logOAuthFailed("google", "No authorization code received");
    return NextResponse.redirect(
      `${origin}/auth/login?error=${encodeURIComponent("No authorization code received")}`
    );
  }

  const redirectUrl = `${origin}${next}`;

  try {
    const { supabase, getResponse } = createOAuthCallbackClient(
      request,
      redirectUrl
    );
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);

    if (error || !data.user) {
      authLogger.logOAuthFailed("google", error?.message ?? "Code exchange failed");
      return NextResponse.redirect(
        `${origin}/auth/login?error=${encodeURIComponent(error?.message ?? "Could not authenticate")}`
      );
    }

    authLogger.logOAuthCompleted(
      data.user.id,
      data.user.app_metadata?.provider ?? "google"
    );

    return getResponse();
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Authentication failed unexpectedly";
    authLogger.logOAuthFailed("google", message);
    return NextResponse.redirect(
      `${origin}/auth/login?error=${encodeURIComponent(message)}`
    );
  }
}
