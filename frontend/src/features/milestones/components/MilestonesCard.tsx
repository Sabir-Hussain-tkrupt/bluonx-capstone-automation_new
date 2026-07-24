import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast/useToast';
import { useMilestonesForTask } from '@/features/milestones/hooks/useMilestonesForTask';
import { useCreateMilestone } from '@/features/milestones/hooks/useCreateMilestone';
import { formatMilestoneDate } from '@/features/milestones/utils/formatDate';
import { buildMilestonePath } from '@/features/milestones/utils/buildMilestonePath';
import { MilestoneFormModal, type MilestoneFormValues } from './MilestoneFormModal';
import { MilestoneStatusBadge } from './MilestoneStatusBadge';

interface MilestonesCardProps {
  taskId: string;
  projectId: string;
  /** The task's active contract status. A completed contract has already passed
   *  the mark-complete gate (all milestones closed), so no new milestone may be
   *  added — the backend also rejects it with 409. */
  contractStatus?: string;
}

export function MilestonesCard({ taskId, projectId, contractStatus }: MilestonesCardProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data: milestones = [], isLoading } = useMilestonesForTask(taskId);
  const createMutation = useCreateMilestone();
  const [showForm, setShowForm] = useState(false);
  const canAddMilestone = contractStatus !== 'completed';

  const handleCreate = (data: MilestoneFormValues) => {
    createMutation.mutate(
      {
        task_id: taskId,
        name: data.name,
        start_date: data.start_date,
        end_date: data.end_date,
        notes: data.notes ?? null,
      },
      {
        onSuccess: () => {
          setShowForm(false);
          toast({ variant: 'success', message: 'Milestone created.' });
        },
        onError: (err) => {
          toast({
            variant: 'danger',
            message: (err as { message?: string })?.message || 'Failed to create milestone.',
          });
        },
      },
    );
  };

  return (
    <Card>
      <div className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-secondary-900">Milestones</h3>
          {canAddMilestone && (
            <Button size="sm" onClick={() => setShowForm(true)}>
              Add Milestone
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton height="44px" />
            <Skeleton height="44px" />
          </div>
        ) : milestones.length === 0 ? (
          <p className="py-6 text-center text-sm text-secondary-500">No milestones yet.</p>
        ) : (
          <ul className="divide-y divide-secondary-100">
            {milestones.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => navigate(buildMilestonePath(projectId, taskId, m.id))}
                  className="flex w-full cursor-pointer items-center justify-between gap-4 py-3 text-left transition-colors hover:bg-secondary-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-secondary-900">{m.name}</p>
                    <p className="mt-0.5 text-xs text-secondary-500">
                      {formatMilestoneDate(m.start_date)} &ndash; {formatMilestoneDate(m.end_date)}
                    </p>
                  </div>
                  <MilestoneStatusBadge status={m.status} size="sm" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <MilestoneFormModal
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        onSubmit={handleCreate}
        isLoading={createMutation.isPending}
      />
    </Card>
  );
}
