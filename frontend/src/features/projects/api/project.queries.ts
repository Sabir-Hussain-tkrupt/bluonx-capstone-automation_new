import { supabase } from '@/lib/supabase';
import { api, fromSupabaseError } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import { toNumberOrNull } from '@/lib/format';

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
  archived_at: string | null;
  archived_by: string | null;
  /**
   * Present only on a create/update response when geocoding could not refresh
   * this record's coordinates. Non-fatal: the write succeeded. Surfaced as a
   * warning toast so the user learns at save time rather than never.
   */
  geocode_warning?: string | null;
}

export interface ProjectListFilters {
  search?: string;
  status?: string;
  archived?: boolean;
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

// ─── Reads ────────────────────────────────────────────────────────────

/** Numeric columns arrive as strings over FastAPI; pin them to `number`. */
function normalizeProject(row: Project): Project {
  return {
    ...row,
    latitude: toNumberOrNull(row.latitude),
    longitude: toNumberOrNull(row.longitude),
    budget: toNumberOrNull(row.budget),
  };
}

/**
 * Fetch projects with optional search, filter, sort, and pagination.
 *
 * Goes through FastAPI rather than Supabase directly. GET /projects already
 * enforces a sort-column allow-list, a page-size ceiling, LIKE-metacharacter
 * escaping on search, and a count-first fetch so a page past the last row
 * returns an empty page instead of a 416. Reading Supabase directly here meant
 * re-implementing all of that, badly, in a second place. Detail reads still go
 * direct (see fetchProjectById).
 */
export async function fetchProjects(filters?: ProjectListFilters): Promise<PaginatedProjects> {
  const { data } = await api.get<PaginatedProjects>(API_ENDPOINTS.PROJECTS, {
    params: {
      search: filters?.search || undefined,
      // The archived-only view has no status sub-filter; the backend applies
      // `status` regardless, so omit it when asking for archived only.
      status: filters?.archived ? undefined : filters?.status || undefined,
      archived_only: filters?.archived || undefined,
      sort_by: filters?.sort_by,
      sort_dir: filters?.sort_dir,
      page: filters?.page,
      page_size: filters?.page_size,
    },
  });

  return { ...data, items: (data.items ?? []).map(normalizeProject) };
}

/**
 * Fetch a single project by ID. Direct Supabase read (RLS-protected).
 */
export async function fetchProjectById(id: string): Promise<Project> {
  const { data, error } = await supabase
    .from('projects')
    .select('*')
    .eq('id', id)
    .is('deleted_at', null)
    .single();

  if (error) throw fromSupabaseError(error, error.code === 'PGRST116' ? 404 : 0);

  return normalizeProject(data as unknown as Project);
}
