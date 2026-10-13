// ─────────────────────────────────────────────────────────────────────────────
// Supabase client singleton
// Fill in your project URL and anon key from:
//   Supabase Dashboard → Project Settings → API
// ─────────────────────────────────────────────────────────────────────────────
import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL  = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_ANON = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!SUPABASE_URL || !SUPABASE_ANON) {
  console.warn(
    '[Supabase] Missing env vars VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. ' +
    'Create frontend/.env.local with your project credentials.'
  )
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON)
