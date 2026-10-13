import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

const AuthContext = createContext(null)

/**
 * Wraps the app — provides current session/user and sign-out helper.
 * Children only render once we know the auth state (avoids flash).
 */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(undefined)   // undefined = still loading

  useEffect(() => {
    // Grab the active session on mount
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session ?? null)
    })

    // Subscribe to future auth state changes (login / logout / token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
    })

    return () => subscription.unsubscribe()
  }, [])

  const signOut = async () => {
    await supabase.auth.signOut()
    setSession(null)
  }

  return (
    <AuthContext.Provider value={{ session, user: session?.user ?? null, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

/** Convenience hook — use in any component that needs auth state */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
