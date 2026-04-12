import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';
import type { Trade } from '../types';

export async function fetchTrades(): Promise<Trade[]> {
  const { data, error } = await supabase
    .from('trades')
    .select('*')
    .eq('is_active', true)
    .order('phase')
    .order('name');

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  return (data ?? []) as unknown as Trade[];
}
