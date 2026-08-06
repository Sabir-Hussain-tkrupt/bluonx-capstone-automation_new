import { supabase } from '@/lib/supabase';
import { fromSupabaseError } from '@/lib/api';
import type { Trade } from '../types';

export async function fetchTrades(): Promise<Trade[]> {
  const { data, error } = await supabase
    .from('trades')
    .select('*')
    .eq('is_active', true)
    .order('phase')
    .order('name');

  if (error) throw fromSupabaseError(error);

  return (data ?? []) as unknown as Trade[];
}
