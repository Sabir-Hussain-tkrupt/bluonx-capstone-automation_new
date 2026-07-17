import { useState } from 'react';
import { StarRating } from '@/components/ui/StarRating';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast/useToast';
import { formatMilestoneDate } from '@/features/milestones/utils/formatDate';
import type { Milestone } from '@/features/milestones/api/milestone.queries';
import type { VendorPerformanceReview } from '@/features/contracts/api/review.queries';
import { useCreateReview, useUpdateReview } from '@/features/contracts/hooks/useReviewMutations';

interface ReviewPanelProps {
  contractId: string;
  existingReview: VendorPerformanceReview | null;
  /** The contract's milestones, shown read-only as decision-support for the rating. */
  milestones: Milestone[];
}

/** Late = finished after the originally committed (baseline) end date. */
function isLate(m: Milestone): boolean {
  return !!m.actual_end_date && m.actual_end_date > m.baseline_end_date;
}

function MilestoneFacts({ milestones }: { milestones: Milestone[] }) {
  if (milestones.length === 0) {
    return <p className="text-sm text-secondary-500">No milestones on this contract.</p>;
  }
  return (
    <ul className="divide-y divide-secondary-100 rounded-lg border border-secondary-200">
      {milestones.map((m) => {
        const troubled = m.status === 'delayed' || m.status === 'unresponsive';
        return (
          <li key={m.id} className="flex items-center justify-between gap-4 px-3 py-2 text-sm">
            <span className="min-w-0 truncate font-medium text-secondary-900">{m.name}</span>
            <span className="flex items-center gap-2 whitespace-nowrap text-xs text-secondary-500">
              <span>
                committed {formatMilestoneDate(m.baseline_end_date)} · actual{' '}
                {formatMilestoneDate(m.actual_end_date)}
              </span>
              {isLate(m) && (
                <span className="rounded bg-warning-100 px-1.5 py-0.5 font-medium text-warning-700">
                  late
                </span>
              )}
              {troubled && (
                <span className="rounded bg-danger-100 px-1.5 py-0.5 font-medium text-danger-700">
                  {m.status}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function ReviewPanel({ contractId, existingReview, milestones }: ReviewPanelProps) {
  const { toast } = useToast();
  const createMutation = useCreateReview(contractId);
  const updateMutation = useUpdateReview(contractId);

  // Edit mode is implicit when there's no review yet; explicit when the PM clicks Edit.
  const [isEditing, setIsEditing] = useState(false);
  const [rating, setRating] = useState<number | null>(existingReview?.rating ?? null);
  const [notes, setNotes] = useState<string>(existingReview?.notes ?? '');

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const showForm = !existingReview || isEditing;

  const handleSave = () => {
    if (rating == null) {
      toast({ variant: 'warning', message: 'Pick a 1-5 rating first.' });
      return;
    }
    const input = { rating, notes: notes.trim() ? notes.trim() : null };
    const onDone = {
      onSuccess: () => {
        setIsEditing(false);
        toast({ variant: 'success', message: 'Rating saved.' });
      },
      onError: (err: unknown) =>
        toast({
          variant: 'danger',
          message: (err as { message?: string })?.message || 'Failed to save rating.',
        }),
    };
    if (existingReview) {
      updateMutation.mutate({ reviewId: existingReview.id, input }, onDone);
    } else {
      createMutation.mutate(input, onDone);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-secondary-500 uppercase">
          Milestone history
        </h4>
        <MilestoneFacts milestones={milestones} />
      </div>

      {showForm ? (
        <div className="space-y-3">
          {!existingReview && (
            <p className="text-sm text-secondary-600">Rate this vendor&apos;s performance?</p>
          )}
          <StarRating value={rating} onChange={setRating} size="lg" label="Vendor rating" />
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            aria-label="Performance notes"
            placeholder="Optional notes about this vendor's performance..."
            className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={handleSave} isLoading={isSaving}>
              {existingReview ? 'Save Changes' : 'Save Rating'}
            </Button>
            {existingReview && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setIsEditing(false);
                  setRating(existingReview.rating);
                  setNotes(existingReview.notes ?? '');
                }}
                disabled={isSaving}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <StarRating value={existingReview.rating} readOnly size="md" />
            {existingReview.notes && (
              <p className="text-sm text-secondary-600">{existingReview.notes}</p>
            )}
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              // Seed the form from the persisted review so an edit always starts
              // from the current saved values, not stale local state.
              setRating(existingReview.rating);
              setNotes(existingReview.notes ?? '');
              setIsEditing(true);
            }}
          >
            Edit
          </Button>
        </div>
      )}
    </div>
  );
}
