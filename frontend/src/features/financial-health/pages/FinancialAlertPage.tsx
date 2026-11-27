import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatDateTime, textareaClass } from '@/features/contingency/components/shared';
import { formatMoney } from '@/features/budgets/utils/money';
import { HealthNumbers } from '../components/HealthNumbers';
import { LiftHoldModal } from '../components/LiftHoldModal';
import { ALERT_STATUS, ALERT_TYPE_LABELS, SEVERITY_VARIANT, needsDecision } from '../constants';
import { useDecideAlert, useFinancialAlert } from '../hooks/useFinancialHealth';
import type { FinancialAlertDetail } from '../types';

/** Task 5.4 — the decision screen every alert notification and email opens. */
export function FinancialAlertPage() {
  const { id = '' } = useParams<{ id: string }>();
  const query = useFinancialAlert(id);

  if (query.isLoading) return <Skeleton height="400px" />;
  if (query.isError || !query.data) {
    return (
      <Alert variant="danger" title="Could not load the alert">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(query.error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>Retry</Button>
        </div>
      </Alert>
    );
  }
  return <AlertView key={id} alert={query.data} />;
}

function AlertView({ alert: a }: { alert: FinancialAlertDetail }) {
  const [showLift, setShowLift] = useState(false);
  const others = a.health.alerts.filter((x) => x.id !== a.id && needsDecision(x.status));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-secondary-900">{ALERT_TYPE_LABELS[a.alert_type]}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-secondary-500">
            <Link to={`/projects/${a.project_id}?tab=budget`} className="font-medium text-primary-600 hover:underline">
              {a.project_name}
            </Link>
            <StatusBadge status={a.severity} variant={SEVERITY_VARIANT[a.severity]} size="sm" />
            <StatusBadge status={ALERT_STATUS[a.status].label} variant={ALERT_STATUS[a.status].variant} size="sm" />
            <span>Opened {formatDateTime(a.created_at)}</span>
          </div>
        </div>
        {a.permissions.can_lift && <Button onClick={() => setShowLift(true)}>Lift hold</Button>}
      </div>

      <Alert variant={needsDecision(a.status) ? SEVERITY_VARIANT[a.severity] : 'neutral'} title="What triggered it">
        {a.message}
      </Alert>

      <Card title="Project health now" padding="md">
        <HealthNumbers health={a.health} />
        {a.health.reserve != null && (
          <p className="mt-4 text-sm text-secondary-600">
            Long-tail reserve: <strong className="text-secondary-900">{formatMoney(a.health.reserve)}</strong>
          </p>
        )}
      </Card>

      {a.decision && (
        <Card title="Decision" padding="md">
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <Item label="Decision" value={a.decision === 'hold' ? 'Not OK: project on hold' : 'OK to proceed'} />
            <Item label="Decided by" value={`${a.decided_by_name ?? '—'} · ${formatDateTime(a.decided_at)}`} />
            <Item label="Reason" value={a.decision_reason ?? '—'} />
            <Item label="Spoke with" value={a.discussed_with_name ?? '—'} />
            <Item label="What was discussed" value={a.conversation_notes ?? '—'} />
            {a.hold_lifted_at && (
              <Item
                label="Hold lifted"
                value={`${a.hold_lifted_by_name ?? '—'} · ${formatDateTime(a.hold_lifted_at)}: ${a.hold_lift_reason ?? ''}`}
              />
            )}
          </dl>
        </Card>
      )}

      {a.permissions.can_decide ? (
        <DecisionForm alert={a} alsoSettles={others.map((x) => ALERT_TYPE_LABELS[x.alert_type])} />
      ) : (
        needsDecision(a.status) && (
          <Alert variant="info" title="Waiting for a decision">
            A project manager, executive or admin decides after talking to the field manager.
          </Alert>
        )
      )}

      {showLift && <LiftHoldModal projectId={a.project_id} onClose={() => setShowLift(false)} />}
    </div>
  );
}

function DecisionForm({ alert, alsoSettles }: { alert: FinancialAlertDetail; alsoSettles: string[] }) {
  const { toast } = useToast();
  const decide = useDecideAlert(alert.id);
  const preset = alert.field_managers.some((m) => m.id === alert.health.field_manager_id)
    ? (alert.health.field_manager_id ?? '')
    : '';
  const [discussedWith, setDiscussedWith] = useState(preset);
  const [notes, setNotes] = useState('');
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<{ who?: string; notes?: string; reason?: string }>({});

  const submit = (decision: 'proceed' | 'hold') => {
    const next: typeof errors = {};
    if (!discussedWith) next.who = 'Select the field manager you spoke with.';
    if (!notes.trim()) next.notes = 'Record what was discussed.';
    if (!reason.trim()) next.reason = 'Give the reason for the decision.';
    setErrors(next);
    if (Object.keys(next).length) return;
    decide.mutate(
      { decision, reason: reason.trim(), discussed_with: discussedWith, conversation_notes: notes.trim() },
      {
        onSuccess: () =>
          toast({
            variant: 'success',
            message: decision === 'hold' ? 'Project placed on hold.' : 'OK to proceed recorded.',
          }),
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the decision.') }),
      },
    );
  };

  return (
    <Card title="Record the decision" subtitle="Talk to the field manager first, then decide." padding="md">
      <div className="space-y-4">
        {alert.field_managers.length === 0 && (
          <Alert variant="warning" title="No field manager to select">
            Give someone else the Field Manager role (Settings → Users) to record the conversation.
          </Alert>
        )}
        {alsoSettles.length > 0 && (
          <p className="text-sm text-secondary-600">
            This decision also settles the project's other open alerts: {alsoSettles.join(', ')}.
          </p>
        )}
        <FormField label="Field manager you spoke with" htmlFor="fa-who" required error={errors.who}>
          <Select
            id="fa-who"
            placeholder="Select a field manager"
            options={alert.field_managers.map((m) => ({ value: m.id, label: m.name }))}
            value={discussedWith}
            onChange={(e) => setDiscussedWith(e.target.value)}
          />
        </FormField>
        <FormField label="What was discussed" htmlFor="fa-notes" required error={errors.notes}>
          <textarea id="fa-notes" rows={3} maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)} className={textareaClass} />
        </FormField>
        <FormField
          label="Reason for the decision"
          htmlFor="fa-reason"
          required
          error={errors.reason}
          hint="Hold blocks new bid packages, awards, approvals and payments until it is lifted. Plan savings elsewhere, or request a top-up on the Budget tab."
        >
          <textarea id="fa-reason" rows={3} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} className={textareaClass} />
        </FormField>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="danger" onClick={() => submit('hold')} disabled={decide.isPending}>Not OK: hold project</Button>
          <Button onClick={() => submit('proceed')} isLoading={decide.isPending}>OK to proceed</Button>
        </div>
      </div>
    </Card>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-secondary-500">{label}</dt>
      <dd className="whitespace-pre-wrap text-secondary-900">{value}</dd>
    </div>
  );
}
