import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────
/**
 * Project row shape.
 *
 * Temporary type until database.types.ts is fully generated.
 */
export interface Project {
  id: string;
  project_name: string;
  project_code: string | null;
  project_type: string;
  address_line1: string;
  city: string;
  state: string;
  zip_code: string;
  latitude: number | null;
  longitude: number | null;
  project_status: string;
  start_date: string | null;
  estimated_end_date: string | null;
  total_budget: number | null;
  notes: string | null;
  created_by: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Supabase Direct Reads ────────────────────────────────────────────

/**
 * Fetch all projects. RLS ensures only authenticated users see data.
 */
export async function fetchProjects(): Promise<Project[]> {
  const { data, error } = await supabase
    .from('projects')
    .select('*')
    .is('deleted_at', null)
    .order('created_at', { ascending: false });

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  // Cast through unknown because database.types.ts is a placeholder.
  // Once full types are generated, these casts can be removed.
  return (data ?? []) as unknown as Project[];
}

/**
 * Fetch a single project by ID.
 */
export async function fetchProjectById(id: string): Promise<Project> {
  const { data, error } = await supabase
    .from('projects')
    .select('*')
    .eq('id', id)
    .single();

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: error.code === 'PGRST116' ? 404 : 0,
      details: error,
    };
    throw apiError;
  }

  return data as unknown as Project;
}
