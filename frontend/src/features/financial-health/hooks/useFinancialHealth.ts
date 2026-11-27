import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { API_ENDPOINTS } from '@/constants/api';
import type { DecisionInput, FinancialAlert, FinancialAlertDetail, FinancialHealth, HealthSetupInput } from '../types';

export function useFinancialHealth(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.budgets.health(projectId),
    queryFn: async () => (await api.get<FinancialHealth>(API_ENDPOINTS.PROJECT_FINANCIAL_HEALTH(projectId))).data,
    enabled: !!projectId && enabled,
  });
}

export function useFinancialAlerts() {
  return useQuery({
    queryKey: queryKeys.financialAlerts.list(),
    queryFn: async () => (await api.get<FinancialAlert[]>(API_ENDPOINTS.FINANCIAL_ALERTS)).data,
  });
}

export function useFinancialAlert(id: string) {
  return useQuery({
    queryKey: queryKeys.financialAlerts.detail(id),
    queryFn: async () => (await api.get<FinancialAlertDetail>(API_ENDPOINTS.FINANCIAL_ALERT(id))).data,
    enabled: !!id,
  });
}

/** A decision can change the project's status: refresh that too. */
function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.financialAlerts.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
  };
}

export function useUpdateHealthSetup(projectId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (body: HealthSetupInput) =>
      (await api.put<FinancialHealth>(API_ENDPOINTS.PROJECT_FINANCIAL_HEALTH_SETUP(projectId), body)).data,
    onSuccess,
  });
}

export function useRecordGroundbreaking(projectId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async () =>
      (await api.post<FinancialHealth>(API_ENDPOINTS.PROJECT_GROUNDBREAKING(projectId))).data,
    onSuccess,
  });
}

export function useLiftHold(projectId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (reason: string) =>
      (await api.post<FinancialHealth>(API_ENDPOINTS.PROJECT_LIFT_HOLD(projectId), { reason })).data,
    onSuccess,
  });
}

export function useDecideAlert(alertId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (body: DecisionInput) =>
      (await api.post<FinancialAlertDetail>(API_ENDPOINTS.FINANCIAL_ALERT_DECISION(alertId), body)).data,
    onSuccess,
  });
}
