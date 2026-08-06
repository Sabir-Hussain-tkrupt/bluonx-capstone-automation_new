import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { errorMessage } from '@/lib/api';
import { useTrades } from '../hooks/useTrades';
import { TRADE_PHASE_LABELS, TRADE_PHASE_ORDER } from '../types';
import type { Trade, TradePhase } from '../types';
import { CreateTradeModal } from './CreateTradeModal';

const phaseSubtitles: Record<TradePhase, string> = {
  due_diligence: 'Investigation work (geotech, surveys, environmental, etc.)',
  development: 'Construction work (grading, utilities, paving, etc.)',
  both: 'Trades used across both Due Diligence and Development phases.',
};

export function TradeManagementPanel() {
  const { data, isLoading, isError, error, refetch } = useTrades();
  const [isModalOpen, setModalOpen] = useState(false);

  const grouped = useMemo(() => {
    const buckets: Record<TradePhase, Trade[]> = {
      due_diligence: [],
      development: [],
      both: [],
    };
    for (const trade of data ?? []) {
      if (buckets[trade.phase]) {
        buckets[trade.phase].push(trade);
      }
    }
    for (const key of TRADE_PHASE_ORDER) {
      buckets[key].sort((a, b) => a.name.localeCompare(b.name));
    }
    return buckets;
  }, [data]);

  const totalCount = data?.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-secondary-500">
          {data
            ? `${totalCount} active trade${totalCount === 1 ? '' : 's'} across all phases.`
            : 'Loading trades…'}
        </p>
        <Button onClick={() => setModalOpen(true)} leftIcon={<PlusIcon />}>
          New Trade
        </Button>
      </div>

      {isError && (
        <Alert
          variant="danger"
          title="Could not load trades"
          dismissible
          onDismiss={() => refetch()}
        >
          {errorMessage(error, 'Please try again.')}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {TRADE_PHASE_ORDER.map((phase) => (
          <Card key={phase} title={TRADE_PHASE_LABELS[phase]} subtitle={phaseSubtitles[phase]}>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton variant="rectangular" height="32px" />
                <Skeleton variant="rectangular" height="32px" />
                <Skeleton variant="rectangular" height="32px" />
              </div>
            ) : grouped[phase].length === 0 ? (
              <EmptyState
                title="No trades yet"
                description={`No trades configured for ${TRADE_PHASE_LABELS[phase].toLowerCase()}.`}
              />
            ) : (
              <ul className="divide-y divide-secondary-100">
                {grouped[phase].map((trade) => (
                  <li
                    key={trade.id}
                    className="flex items-center justify-between py-2 text-sm text-secondary-800"
                  >
                    <span className="truncate">{trade.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>

      <CreateTradeModal isOpen={isModalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}

function PlusIcon() {
  return <Plus className="h-4 w-4" aria-hidden="true" />;
}
