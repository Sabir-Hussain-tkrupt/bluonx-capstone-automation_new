import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  addBudgetLine,
  addLandClosing,
  addTemplateLine,
  applyBudgetImport,
  baselineBudget,
  createBudget,
  deleteTemplateLine,
  fetchBudgetLines,
  fetchBudgetSummary,
  fetchDefaultTemplate,
  fetchLandClosings,
  previewBudgetImport,
  removeBudgetLine,
  reorderBudgetLines,
  reorderTemplateLines,
  resetBudget,
  syncAwards,
  updateBudgetLine,
  updateLandClosing,
  updateTemplateLine,
  type ClosingInput,
  type TemplateLineInput,
} from '../api/budget.api';
import type { BudgetLineInput, ImportPreviewRow } from '../types';

// ─── Reads ────────────────────────────────────────────────────────────

export function useBudgetLines(projectId: string) {
  return useQuery({
    queryKey: queryKeys.budgets.lines(projectId),
    queryFn: () => fetchBudgetLines(projectId),
    enabled: !!projectId,
  });
}

export function useBudgetSummary(projectId: string) {
  return useQuery({
    queryKey: queryKeys.budgets.summary(projectId),
    queryFn: () => fetchBudgetSummary(projectId),
    enabled: !!projectId,
  });
}

export function useLandClosings(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.budgets.closings(projectId),
    queryFn: () => fetchLandClosings(projectId),
    enabled: !!projectId && enabled,
  });
}

export function useDefaultBudgetTemplate() {
  return useQuery({
    queryKey: queryKeys.budgetTemplates.default(),
    queryFn: fetchDefaultTemplate,
  });
}

// ─── Writes ───────────────────────────────────────────────────────────

/** Every budget write can move totals, contingency and tasks: refresh them all. */
function useInvalidateBudget(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.project(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(projectId) });
  };
}

export function useCreateBudget(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: (body: { contingency_percent?: string } = {}) => createBudget(projectId, body),
    onSuccess: invalidate,
  });
}

export function useBaselineBudget(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({ mutationFn: () => baselineBudget(projectId), onSuccess: invalidate });
}

export function useResetBudget(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({ mutationFn: () => resetBudget(projectId), onSuccess: invalidate });
}

export function useSyncAwards(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({ mutationFn: () => syncAwards(projectId), onSuccess: invalidate });
}

export function useAddBudgetLine(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({ mutationFn: (body: BudgetLineInput) => addBudgetLine(projectId, body), onSuccess: invalidate });
}

export function useUpdateBudgetLine(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: BudgetLineInput }) => updateBudgetLine(lineId, body),
    onSuccess: invalidate,
  });
}

export function useRemoveBudgetLine(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({ mutationFn: (lineId: string) => removeBudgetLine(lineId), onSuccess: invalidate });
}

export function useReorderBudgetLines(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: (lineIds: string[]) => reorderBudgetLines(projectId, lineIds),
    onSuccess: invalidate,
  });
}

export function useAddLandClosing(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: ClosingInput }) => addLandClosing(lineId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateLandClosing(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: ({ closingId, body }: { closingId: string; body: ClosingInput }) => updateLandClosing(closingId, body),
    onSuccess: invalidate,
  });
}

export function usePreviewBudgetImport(projectId: string) {
  return useMutation({ mutationFn: (file: File) => previewBudgetImport(projectId, file) });
}

export function useApplyBudgetImport(projectId: string) {
  const invalidate = useInvalidateBudget(projectId);
  return useMutation({
    mutationFn: (rows: ImportPreviewRow[]) => applyBudgetImport(projectId, rows),
    onSuccess: invalidate,
  });
}

// ─── Template ─────────────────────────────────────────────────────────

function useInvalidateTemplate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.budgetTemplates.all });
}

export function useAddTemplateLine(templateId: string) {
  const invalidate = useInvalidateTemplate();
  return useMutation({ mutationFn: (body: TemplateLineInput) => addTemplateLine(templateId, body), onSuccess: invalidate });
}

export function useUpdateTemplateLine() {
  const invalidate = useInvalidateTemplate();
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: TemplateLineInput }) => updateTemplateLine(lineId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteTemplateLine() {
  const invalidate = useInvalidateTemplate();
  return useMutation({ mutationFn: (lineId: string) => deleteTemplateLine(lineId), onSuccess: invalidate });
}

export function useReorderTemplateLines(templateId: string) {
  const invalidate = useInvalidateTemplate();
  return useMutation({
    mutationFn: (lineIds: string[]) => reorderTemplateLines(templateId, lineIds),
    onSuccess: invalidate,
  });
}
