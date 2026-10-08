import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { taskTemplateService } from '../services/taskTemplateService';
import type {
  TaskTemplateFilters,
  TaskTemplateFormData,
} from '../types/taskTemplate.types';

export function useTaskTemplates(filters?: TaskTemplateFilters) {
  return useQuery({
    queryKey: queryKeys.taskTemplates.list(filters as Record<string, unknown>),
    queryFn: () => taskTemplateService.getTaskTemplates(filters),
  });
}

export function useTaskTemplate(id: string | null) {
  return useQuery({
    queryKey: queryKeys.taskTemplates.detail(id || ''),
    queryFn: () => taskTemplateService.getTaskTemplate(id!),
    enabled: !!id,
  });
}

export function useCreateTaskTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TaskTemplateFormData) =>
      taskTemplateService.createTaskTemplate(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTemplates.all });
    },
  });
}

export function useUpdateTaskTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<TaskTemplateFormData> }) =>
      taskTemplateService.updateTaskTemplate(id, payload),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTemplates.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTemplates.detail(id) });
    },
  });
}

export function useDeleteTaskTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => taskTemplateService.deleteTaskTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTemplates.all });
    },
  });
}
