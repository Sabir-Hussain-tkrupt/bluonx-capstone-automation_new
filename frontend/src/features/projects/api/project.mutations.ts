import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Project } from './project.queries';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface CreateProjectInput {
  name: string;
  description?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  budget?: number;
  status?: string;
  start_date?: string;
  estimated_end_date?: string;
}

export interface UpdateProjectInput {
  id: string;
  name?: string;
  description?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  budget?: number;
  status?: string;
  start_date?: string;
  estimated_end_date?: string;
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

export async function createProject(input: CreateProjectInput): Promise<Project> {
  const { data } = await api.post<Project>(API_ENDPOINTS.PROJECTS, input);
  return data;
}

export async function updateProject({ id, ...input }: UpdateProjectInput): Promise<Project> {
  const { data } = await api.patch<Project>(API_ENDPOINTS.PROJECT(id), input);
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.PROJECT(id));
}

export async function archiveProject(id: string): Promise<Project> {
  const { data } = await api.post<Project>(`${API_ENDPOINTS.PROJECT(id)}/archive`);
  return data;
}

export async function unarchiveProject(id: string): Promise<Project> {
  const { data } = await api.post<Project>(`${API_ENDPOINTS.PROJECT(id)}/unarchive`);
  return data;
}
