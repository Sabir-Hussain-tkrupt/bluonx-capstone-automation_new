export interface TaskTemplate {
  id: string;
  name: string;
  description: string | null;
  phase: 'due_diligence' | 'development';
  trade_id: string;
  trade_name?: string | null;
  bid_type: 'competitive' | 'internal' | 'direct_assign';
  budget_estimate: number;
  sort_order: number;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskTemplateFormData {
  name: string;
  description?: string | null;
  phase: 'due_diligence' | 'development';
  trade_id: string;
  bid_type: 'competitive' | 'internal' | 'direct_assign';
  budget_estimate: number;
  sort_order?: number;
  is_active: boolean;
}

export interface TaskTemplateListResponse {
  items: TaskTemplate[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskTemplateFilters {
  search?: string;
  phase?: 'due_diligence' | 'development';
  trade_id?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}
