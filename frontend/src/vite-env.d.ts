/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  readonly VITE_API_BASE_URL: string;
  /**
   * Controls the vendor portal API layer.
   * `'true'`  → use the in-memory mock (portalApi.mock.ts) and show the
   *             amber "Demo Mode" banner.
   * `'false'` → use real Axios calls (portalApi.real.ts).
   * String literal union (Vite env values are always strings) catches
   * typos like `=== true` at compile time.
   */
  readonly VITE_DEMO_MODE: 'true' | 'false';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
