import { createClient } from '@supabase/supabase-js';
import type { Database } from '@/types/database.types';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing Supabase environment variables. ' +
    'Ensure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set in .env.local'
  );
}

export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey, {
  auth: {
    // Use localStorage for session persistence across browser tabs/refreshes.
    // When the user closes the browser and reopens, they stay logged in
    // until the refresh token expires (default: 7 days in Supabase).
    persistSession: true,

    // Supabase stores session data in localStorage under this key.
    // Custom key prevents collision if other Supabase projects run on localhost.
    storageKey: 'bluonx-auth',

    // Automatically refresh the JWT before it expires.
    // Supabase handles this internally — it refreshes ~60 seconds before expiry.
    // You don't need to write any refresh logic yourself.
    autoRefreshToken: true,

    // Listen for auth events across browser tabs (login in one tab = logged in everywhere).
    detectSessionInUrl: true,
  },
});