import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { CreateTradeInput, Trade, TradeUsage, UpdateTradeInput } from '../types';

export async function createTrade(input: CreateTradeInput): Promise<Trade> {
  const { data } = await api.post(API_ENDPOINTS.TRADES, input);
  return data as Trade;
}

/** Name / phase change only while nothing uses the trade (server returns 409 otherwise). */
export async function updateTrade(id: string, input: UpdateTradeInput): Promise<Trade> {
  const { data } = await api.patch(API_ENDPOINTS.TRADE(id), input);
  return data as Trade;
}

/** Hard delete; refused (409) while the trade is used or has subtrades. */
export async function deleteTrade(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.TRADE(id));
}

export async function fetchTradeUsage(id: string): Promise<TradeUsage> {
  const { data } = await api.get(API_ENDPOINTS.TRADE_USAGE(id));
  return data as TradeUsage;
}
