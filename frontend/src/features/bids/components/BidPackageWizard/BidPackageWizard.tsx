import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCreateBidPackage } from '@/features/bids/hooks/useCreateBidPackage';
import { ConfigureStep } from './ConfigureStep';
import { VendorSelectionStep } from './VendorSelectionStep';
import { ReviewStep } from './ReviewStep';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData, VendorSelection } from '@/features/bids/types';
import { cn } from '@/utils/cn';

interface BidPackageWizardProps {
  projectId: string;
  taskId: string;
  task: Task;
}

const STEPS = [
  { number: 1, label: 'Configure' },
  { number: 2, label: 'Select Vendors' },
  { number: 3, label: 'Review & Send' },
] as const;

function getDefaultDeadline(): string {
  const date = new Date();
  date.setDate(date.getDate() + 14);
  // Format as datetime-local value: YYYY-MM-DDTHH:mm
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}T17:00`;
}

export function BidPackageWizard({ projectId, taskId, task }: BidPackageWizardProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const createMutation = useCreateBidPackage(taskId);

  const [step, setStep] = useState(1);
  const [wizardData, setWizardData] = useState<WizardData>({
    deadline: getDefaultDeadline(),
    bidTemplateId: null,
    documentIds: null,
    vendorSelections: [],
    instructions: '',
    desiredStartDate: null,
  });

  const updateData = (partial: Partial<WizardData>) => {
    setWizardData((prev) => ({ ...prev, ...partial }));
  };

  const handleSubmit = () => {
    if (!wizardData.bidTemplateId) return;

    createMutation.mutate(
      {
        deadline: new Date(wizardData.deadline).toISOString(),
        bid_template_id: wizardData.bidTemplateId,
        project_document_ids: wizardData.documentIds ?? [],
        vendor_selections: wizardData.vendorSelections,
        ...(wizardData.instructions.trim() ? { instructions: wizardData.instructions.trim() } : {}),
        ...(wizardData.desiredStartDate
          ? { desired_start_date: wizardData.desiredStartDate }
          : {}),
      },
      {
        onSuccess: (response) => {
          if (response.invitations_failed > 0) {
            toast({
              variant: 'warning',
              message: `${response.invitations_sent} invitations sent. ${response.invitations_failed} failed — check the detail page for specifics.`,
            });
          } else {
            toast({
              variant: 'success',
              message: `${response.invitations_sent} invitations sent successfully.`,
            });
          }
          navigate(
            `/projects/${projectId}/tasks/${taskId}/bid-packages/${response.bid_package_id}`,
          );
        },
        onError: (err) => {
          toast({
            variant: 'danger',
            message: (err as { message?: string })?.message || 'Failed to create bid package.',
          });
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <nav aria-label="Progress">
        <ol className="flex items-center">
          {STEPS.map((s, idx) => (
            <li
              key={s.number}
              className={cn('flex items-center', idx < STEPS.length - 1 && 'flex-1')}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium',
                    step > s.number
                      ? 'bg-primary-600 text-white'
                      : step === s.number
                        ? 'border-2 border-primary-600 text-primary-600'
                        : 'border-2 border-secondary-300 text-secondary-400',
                  )}
                >
                  {step > s.number ? (
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    s.number
                  )}
                </span>
                <span
                  className={cn(
                    'hidden text-sm font-medium sm:inline',
                    step >= s.number ? 'text-secondary-900' : 'text-secondary-400',
                  )}
                >
                  {s.label}
                </span>
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    'mx-4 h-0.5 flex-1',
                    step > s.number ? 'bg-primary-600' : 'bg-secondary-200',
                  )}
                />
              )}
            </li>
          ))}
        </ol>
      </nav>

      {/* Step Content */}
      {step === 1 && (
        <ConfigureStep
          projectId={projectId}
          task={task}
          data={wizardData}
          onUpdate={updateData}
          onNext={() => setStep(2)}
        />
      )}
      {step === 2 && (
        <VendorSelectionStep
          taskId={taskId}
          data={wizardData}
          onUpdate={(selections: VendorSelection[]) =>
            updateData({ vendorSelections: selections })
          }
          onNext={() => setStep(3)}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && (
        <ReviewStep
          data={wizardData}
          task={task}
          onSubmit={handleSubmit}
          onBack={() => setStep(2)}
          isSubmitting={createMutation.isPending}
        />
      )}
    </div>
  );
}
