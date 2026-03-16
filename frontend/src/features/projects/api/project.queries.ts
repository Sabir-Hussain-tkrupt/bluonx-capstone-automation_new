import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────

export type ProjectStatus = 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled';

/**
 * Project row shape matching the projects table in the database.
 */
export interface Project {
  id: string;
  name: string;
  description: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  latitude: number | null;
  longitude: number | null;
  budget: number | null;
  status: ProjectStatus;
  start_date: string | null;
  estimated_end_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ProjectListFilters {
  search?: string;
  status?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedProjects {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Supabase Direct Reads ────────────────────────────────────────────

/**
 * Fetch projects with optional search, filter, sort, and pagination.
 * RLS ensures only authenticated users see data.
 */
export async function fetchProjects(filters?: ProjectListFilters): Promise<PaginatedProjects> {
  const page = filters?.page ?? 1;
  const pageSize = filters?.page_size ?? 25;
  const sortBy = filters?.sort_by ?? 'name';
  const ascending = (filters?.sort_dir ?? 'asc') !== 'desc';

  let query = supabase
    .from('projects')
    .select('*', { count: 'exact' })
    .is('deleted_at', null);

  if (filters?.search) {
    query = query.ilike('name', `%${filters.search}%`);
  }

  if (filters?.status) {
    query = query.eq('status', filters.status);
  }

  query = query.order(sortBy, { ascending });

  const offset = (page - 1) * pageSize;
  query = query.range(offset, offset + pageSize - 1);

  const { data, error, count } = await query;

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  return {
    items: (data ?? []) as unknown as Project[],
    total: count ?? 0,
    page,
    page_size: pageSize,
  };
}

/**
 * Fetch a single project by ID.
 */
export async function fetchProjectById(id: string): Promise<Project> {
  const { data, error } = await supabase
    .from('projects')
    .select('*')
    .eq('id', id)
    .is('deleted_at', null)
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
