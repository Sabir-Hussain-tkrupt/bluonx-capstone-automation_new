import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { CreateTradeInput, Trade } from '../types';

export async function createTrade(input: CreateTradeInput): Promise<Trade> {
  const { data } = await api.post(API_ENDPOINTS.TRADES, input);
  return data as Trade;
}
