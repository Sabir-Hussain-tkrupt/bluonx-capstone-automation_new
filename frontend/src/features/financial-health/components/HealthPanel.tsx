import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flag, Settings2 } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatMoney, toCents } from '@/features/budgets/utils/money';
import { ALERT_STATUS, ALERT_TYPE_LABELS, SEVERITY_VARIANT, needsDecision } from '../constants';
import { useFinancialHealth, useRecordGroundbreaking } from '../hooks/useFinancialHealth';
import { HealthNumbers } from './HealthNumbers';
import { HealthSetupModal } from './HealthSetupModal';
import { LiftHoldModal } from './LiftHoldModal';

/** Phase 5 — contingency left against work left, the reserve and live alerts. */
export function HealthPanel({ projectId, readOnly = false }: { projectId: string; readOnly?: boolean }) {
  const { toast } = useToast();
  const navigate = useNavigate();
  const query = useFinancialHealth(projectId);
  const groundbreaking = useRecordGroundbreaking(projectId);
  const [showSetup, setShowSetup] = useState(false);
  const [showGroundbreaking, setShowGroundbreaking] = useState(false);
  const [showLift, setShowLift] = useState(false);

  if (query.isLoading) return <Skeleton height="160px" />;
  if (query.isError || !query.data) {
    return (
      <Alert variant="danger" title="Could not load the contingency health">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(query.error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>Retry</Button>
        </div>
      </Alert>
    );
  }

  const h = query.data;
  const canManage = h.permissions.manage && !readOnly;
  const belowReserve = h.reserve != null && toCents(h.contingency) < toCents(h.reserve);

  const record = () =>
    groundbreaking.mutate(undefined, {
      onSuccess: () => {
        setShowGroundbreaking(false);
        toast({ variant: 'success', message: 'Groundbreaking recorded.' });
      },
      onError: (e) => {
        setShowGroundbreaking(false);
        toast({ variant: 'danger', message: errorMessage(e, 'Could not record groundbreaking.') });
      },
    });

  return (
    <Card
      title="Contingency health"
      subtitle="Contingency left must not fall below work left."
      padding="md"
      actions={
        canManage ? (
          <div className="flex flex-wrap gap-2">
            {h.permissions.record_groundbreaking && (
              <Button size="sm" variant="outline" leftIcon={<Flag className="h-4 w-4" />} onClick={() => setShowGroundbreaking(true)}>
                Record groundbreaking
              </Button>
            )}
            <Button size="sm" variant="outline" leftIcon={<Settings2 className="h-4 w-4" />} onClick={() => setShowSetup(true)}>
              Setup
            </Button>
          </div>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {h.financial_hold && (
          <Alert variant="warning" title="Project on financial hold">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span>New bid packages, awards, approvals and payments are blocked until the hold is lifted.</span>
              {canManage && <Button size="sm" variant="outline" onClick={() => setShowLift(true)}>Lift hold</Button>}
            </div>
          </Alert>
        )}

        {h.alerts.map((a) => (
          <Alert
            key={a.id}
            variant={needsDecision(a.status) ? SEVERITY_VARIANT[a.severity] : 'neutral'}
            title={`${ALERT_TYPE_LABELS[a.alert_type]} · ${ALERT_STATUS[a.status].label}`}
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span>
                {a.message}
                {a.decision_reason && ` Reason: ${a.decision_reason}`}
              </span>
              <Button size="sm" variant="outline" onClick={() => navigate(`/financial-alerts/${a.id}`)}>
                {needsDecision(a.status) && canManage ? 'Decide' : 'View'}
              </Button>
            </div>
          </Alert>
        ))}

        <HealthNumbers health={h} />

        <p className="text-sm text-secondary-600">
          Long-tail reserve:{' '}
          <strong className={belowReserve ? 'text-danger-700' : 'text-secondary-900'}>
            {h.reserve != null ? formatMoney(h.reserve) : 'not set'}
          </strong>
          {belowReserve && ' (contingency is below it)'}
        </p>
      </div>

      {showSetup && <HealthSetupModal health={h} onClose={() => setShowSetup(false)} />}
      {showLift && <LiftHoldModal projectId={projectId} onClose={() => setShowLift(false)} />}
      <ConfirmDialog
        isOpen={showGroundbreaking}
        title="Record groundbreaking"
        message={
          <>
            Record groundbreaking with <strong>{formatMoney(h.contingency)}</strong> of contingency? From now on,
            contingency left is measured against this amount. It cannot be changed later.
          </>
        }
        confirmText="Record groundbreaking"
        confirmVariant="primary"
        isLoading={groundbreaking.isPending}
        onConfirm={record}
        onCancel={() => setShowGroundbreaking(false)}
      />
    </Card>
  );
}
