export type TradePhase = 'due_diligence' | 'development' | 'both';

export interface Trade {
  id: string;
  name: string;
  phase: TradePhase;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateTradeInput {
  name: string;
  phase: TradePhase;
}

export const TRADE_PHASE_LABELS: Record<TradePhase, string> = {
  due_diligence: 'Due Diligence',
  development: 'Development',
  both: 'Both Phases',
};

export const TRADE_PHASE_ORDER: TradePhase[] = ['due_diligence', 'development', 'both'];
