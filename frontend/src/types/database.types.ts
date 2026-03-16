/**
 * Placeholder for Supabase-generated database types.
 *
 * Generate the real types by running:
 *   npx supabase gen types typescript --project-id <your-project-id> > src/types/database.types.ts
 *
 * This gives you full autocomplete for all 28 tables, their columns,
 * and the correct TypeScript types for each column.
 */
export type Database = {
  public: {
    Tables: {
      users: {
        Row: {
          id: string;
          email: string;
          full_name: string;
          role: 'admin' | 'project_manager';
          is_active: boolean;
          created_at: string;
          updated_at: string;
          deleted_at: string | null;
        };
        Insert: {
          id: string;
          email: string;
          full_name: string;
          role: 'admin' | 'project_manager';
          is_active?: boolean;
        };
        Update: {
          full_name?: string;
          role?: 'admin' | 'project_manager';
          is_active?: boolean;
          deleted_at?: string | null;
        };
      };
      // Other tables will be auto-generated.
      // This placeholder only includes 'users' since auth needs it.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      [key: string]: any;
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
};