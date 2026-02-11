/**
 * Supabase Auth callback — exchanges the OAuth code for a session.
 *
 * After a user signs in with Google (or any OAuth provider), Supabase
 * redirects here with ?code=... in the query string.  We exchange it
 * server-side for a session cookie, then redirect to /chat.
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/chat";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  // Fallback — redirect to login with error
  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
}
