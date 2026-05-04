import { supabase } from '@/lib/supabase';

export async function fetchOpenTaskCount(): Promise<number> {
  const { count, error } = await supabase
    .from('tasks')
    .select('*', { count: 'exact', head: true })
    .in('status', ['bidding', 'evaluating', 'awarded'])
    .is('deleted_at', null);
  if (error) throw error;
  return count ?? 0;
}

export async function fetchPendingBidCount(): Promise<number> {
  const { count, error } = await supabase
    .from('bid_packages')
    .select('*', { count: 'exact', head: true })
    .eq('status', 'open');
  if (error) throw error;
  return count ?? 0;
}
