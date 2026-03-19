import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Task } from './task.queries';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface CreateTaskInput {
  trade_id: string;
  name: string;
  description?: string;
  phase: string;
  bid_type: string;
  budget_estimate?: number;
}

export interface UpdateTaskInput {
  projectId: string;
  taskId: string;
  name?: string;
  description?: string;
  trade_id?: string;
  phase?: string;
  bid_type?: string;
  budget_estimate?: number;
  sort_order?: number;
  status?: string;
}

export interface ReorderItem {
  task_id: string;
  sort_order: number;
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

export async function createTask(projectId: string, input: CreateTaskInput): Promise<Task> {
  const { data } = await api.post<Task>(API_ENDPOINTS.PROJECT_TASKS(projectId), input);
  return data;
}

export async function updateTask({ projectId, taskId, ...input }: UpdateTaskInput): Promise<Task> {
  const { data } = await api.patch<Task>(API_ENDPOINTS.PROJECT_TASK(projectId, taskId), input);
  return data;
}

export async function deleteTask(projectId: string, taskId: string): Promise<void> {
  await api.delete(API_ENDPOINTS.PROJECT_TASK(projectId, taskId));
}

export async function reorderTasks(projectId: string, items: ReorderItem[]): Promise<void> {
  await api.put(API_ENDPOINTS.PROJECT_TASKS_REORDER(projectId), items);
}
