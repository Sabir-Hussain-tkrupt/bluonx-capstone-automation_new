import { api } from '@/lib/api';
import type {
  TaskTemplate,
  TaskTemplateFilters,
  TaskTemplateFormData,
  TaskTemplateListResponse,
} from '../types/taskTemplate.types';

export const taskTemplateService = {
  getTaskTemplates: async (filters?: TaskTemplateFilters): Promise<TaskTemplateListResponse> => {
    const params = new URLSearchParams();
    if (filters?.search) params.append('search', filters.search);
    if (filters?.phase) params.append('phase', filters.phase);
    if (filters?.trade_id) params.append('trade_id', filters.trade_id);
    if (filters?.is_active !== undefined) params.append('is_active', String(filters.is_active));
    if (filters?.page) params.append('page', String(filters.page));
    if (filters?.page_size) params.append('page_size', String(filters.page_size));
    if (filters?.sort_by) params.append('sort_by', filters.sort_by);
    if (filters?.sort_dir) params.append('sort_dir', filters.sort_dir);

    const { data } = await api.get<TaskTemplateListResponse>('/task-templates', { params });
    return data;
  },

  getTaskTemplate: async (id: string): Promise<TaskTemplate> => {
    const { data } = await api.get<TaskTemplate>(`/task-templates/${id}`);
    return data;
  },

  createTaskTemplate: async (payload: TaskTemplateFormData): Promise<TaskTemplate> => {
    const { data } = await api.post<TaskTemplate>('/task-templates', payload);
    return data;
  },

  updateTaskTemplate: async (id: string, payload: Partial<TaskTemplateFormData>): Promise<TaskTemplate> => {
    const { data } = await api.patch<TaskTemplate>(`/task-templates/${id}`, payload);
    return data;
  },

  deleteTaskTemplate: async (id: string): Promise<void> => {
    await api.delete(`/task-templates/${id}`);
  },
};
