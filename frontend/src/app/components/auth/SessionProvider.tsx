"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { User, Session } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";

interface AuthContext {
  user: User | null;
  session: Session | null;
  loading: boolean;
}

const AuthCtx = createContext<AuthContext>({
  user: null,
  session: null,
  loading: true,
});

export const useAuth = () => useContext(AuthCtx);

export default function SessionProvider({ children }: { children: ReactNode }) {
  const hasSupabaseConfig = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  );

  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(hasSupabaseConfig);

  useEffect(() => {
    // Allow frontend-only landing page mode when backend/auth isn't configured.
    if (!hasSupabaseConfig) {
      return;
    }
    const supabase = createClient();

    // Get initial session
    supabase.auth
      .getSession()
      .then(({ data: { session: s } }) => {
        setSession(s);
        setUser(s?.user ?? null);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });

    // Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setUser(s?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, [hasSupabaseConfig]);

  return (
    <AuthCtx.Provider value={{ user, session, loading }}>
      {children}
    </AuthCtx.Provider>
  );
}
