export type TradePhase = 'due_diligence' | 'development' | 'both';

export interface Trade {
  id: string;
  name: string;
  phase: TradePhase;
  is_active: boolean;
  /** NULL = top-level trade; set = subtrade of that trade (one level). */
  parent_trade_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTradeInput {
  name: string;
  /** Required for a trade; ignored for a subtrade (it uses its parent's phase). */
  phase?: TradePhase;
  parent_trade_id?: string | null;
}

export interface UpdateTradeInput {
  name?: string;
  phase?: TradePhase;
  is_active?: boolean;
}

/** GET /trades/{id}/usage — what references a trade. */
export interface TradeUsage {
  trade_id: string;
  tasks: number;
  vendors: number;
  task_templates: number;
  bid_templates: number;
  budget_template_lines: number;
  variances: number;
  subtrades: number;
  total: number;
  in_use: boolean;
  can_edit: boolean;
  can_delete: boolean;
}

export const TRADE_PHASE_LABELS: Record<TradePhase, string> = {
  due_diligence: 'Due Diligence',
  development: 'Development',
  both: 'Both Phases',
};

export const TRADE_PHASE_ORDER: TradePhase[] = ['due_diligence', 'development', 'both'];
