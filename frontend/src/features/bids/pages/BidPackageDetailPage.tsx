import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { useBidPackageDetail } from '@/features/bids/hooks/useBidPackageDetail';
import { useBidPackageEmailLog } from '@/features/bids/hooks/useBidPackageEmailLog';
import { useResendBidLink } from '@/features/bids/hooks/useResendBidLink';
import { useUpdateInvitationStatus } from '@/features/bids/hooks/useUpdateInvitationStatus';
import { InvitationsTable } from '@/features/bids/components/InvitationsTable';
import { EmailLogTable } from '@/features/bids/components/EmailLogTable';
import { cn } from '@/utils/cn';

function useCountdown(deadline: string) {
  const [remaining, setRemaining] = useState('');
  const [isPassed, setIsPassed] = useState(false);

  useEffect(() => {
    const calc = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining('Deadline passed');
        setIsPassed(true);
        return;
      }
      setIsPassed(false);
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const parts: string[] = [];
      if (days > 0) parts.push(`${days}d`);
      if (hours > 0) parts.push(`${hours}h`);
      if (days === 0) parts.push(`${mins}m`);
      setRemaining(`${parts.join(' ')} remaining`);
    };
    calc();
    const interval = setInterval(calc, 60_000);
    return () => clearInterval(interval);
  }, [deadline]);

  return { remaining, isPassed };
}

export function BidPackageDetailPage() {
  const { id: projectId, taskId, bidPackageId } = useParams<{
    id: string;
    taskId: string;
    bidPackageId: string;
  }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: bp, isLoading, error } = useBidPackageDetail(bidPackageId!);
  const { remaining, isPassed } = useCountdown(bp?.deadline ?? '');

  // Email log — lazy loaded
  const [showEmailLog, setShowEmailLog] = useState(false);
  const { data: emailLog, isLoading: emailLogLoading } = useBidPackageEmailLog(
    bidPackageId!,
    showEmailLog,
  );

  // Mutations
  const resendBidLinkMutation = useResendBidLink(bidPackageId!);
  const statusMutation = useUpdateInvitationStatus(bidPackageId!);

  const [resendingId, setResendingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  const handleResendBidLink = (invitationId: string) => {
    setResendingId(invitationId);
    resendBidLinkMutation.mutate(invitationId, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Bid link resent.' });
        setResendingId(null);
      },
      onError: (err) => {
        toast({
          variant: 'danger',
          message: (err as { message?: string })?.message || 'Failed to resend bid link.',
        });
        setResendingId(null);
      },
    });
  };

  const handleMarkStatus = (invitationId: string, status: 'declined') => {
    setUpdatingId(invitationId);
    statusMutation.mutate(
      { invitationId, status },
      {
        onSuccess: () => {
          toast({
            variant: 'success',
            message: `Invitation marked as ${status.replace('_', ' ')}.`,
          });
          setUpdatingId(null);
        },
        onError: (err) => {
          toast({
            variant: 'danger',
            message: (err as { message?: string })?.message || 'Failed to update status.',
          });
          setUpdatingId(null);
        },
      },
    );
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="60%" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Skeleton height="80px" />
          <Skeleton height="80px" />
          <Skeleton height="80px" />
          <Skeleton height="80px" />
        </div>
        <Skeleton height="300px" />
      </div>
    );
  }

  if (error || !bp) {
    return (
      <Alert variant="danger" title="Bid package not found">
        The bid package you are looking for does not exist.
      </Alert>
    );
  }

  const summary = bp.invitation_summary;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(`/projects/${projectId}/tasks/${taskId}`)}
            className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
              Round {bp.round_number} &mdash; {bp.task_name}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={bp.status} />
              <span
                className={cn(
                  'text-xs',
                  isPassed ? 'font-medium text-danger-600' : 'text-secondary-500',
                )}
              >
                {remaining}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {isPassed && bp.status === 'open' && (
            <Button variant="outline" size="sm" onClick={() => {/* TODO: close bidding */}}>
              Close Bidding
            </Button>
          )}
          {bp.status === 'open' && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setShowCancelConfirm(true)}
            >
              Cancel Bid Package
            </Button>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard
          label="Total Invited"
          value={summary.total}
          color="text-secondary-900"
        />
        <SummaryCard
          label="Submitted"
          value={summary.submitted}
          color="text-success-600"
        />
        <SummaryCard
          label="Pending"
          value={summary.sent + summary.opened}
          color="text-info-600"
        />
        <SummaryCard
          label="Declined / Expired"
          value={summary.declined + summary.expired}
          color="text-secondary-500"
        />
      </div>

      {/* Instructions */}
      {bp.instructions && (
        <div className="rounded-lg border border-info-200 bg-info-50 p-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-info-700">
            Instructions to Vendors
          </h3>
          <p className="whitespace-pre-line text-sm text-info-800">
            {bp.instructions}
          </p>
        </div>
      )}

      {/* Invitations Table */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 text-sm font-semibold text-secondary-900">Invitations</h3>
          <InvitationsTable
            invitations={bp.invitations}
            isLoading={false}
            onResendBidLink={handleResendBidLink}
            onMarkDeclined={(id) => handleMarkStatus(id, 'declined')}
            resendingId={resendingId}
            updatingId={updatingId}
          />
        </div>
      </Card>

      {/* Documents */}
      {bp.documents.length > 0 && (
        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Attached Documents</h3>
            <ul className="space-y-1">
              {bp.documents.map((doc) => (
                <li key={doc.id} className="flex items-center gap-2 text-sm text-secondary-700">
                  <svg
                    className="h-4 w-4 shrink-0 text-secondary-400"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path d="M3 3.5A1.5 1.5 0 014.5 2h6.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0116 6.622V16.5a1.5 1.5 0 01-1.5 1.5h-10A1.5 1.5 0 013 16.5v-13z" />
                  </svg>
                  {doc.file_name ?? 'Unnamed document'}
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* Email Log (lazy) */}
      <Card>
        <div className="p-6">
          <button
            type="button"
            onClick={() => setShowEmailLog(!showEmailLog)}
            className="flex w-full items-center justify-between text-left"
          >
            <h3 className="text-sm font-semibold text-secondary-900">Email Log</h3>
            <svg
              className={cn(
                'h-4 w-4 text-secondary-400 transition-transform',
                showEmailLog && 'rotate-180',
              )}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          {showEmailLog && (
            <div className="mt-4">
              <EmailLogTable
                items={emailLog?.items ?? []}
                isLoading={emailLogLoading}
              />
            </div>
          )}
        </div>
      </Card>

      {/* Cancel Confirmation Modal */}
      <Modal
        isOpen={showCancelConfirm}
        onClose={() => setShowCancelConfirm(false)}
        title="Cancel Bid Package"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowCancelConfirm(false)}>
              Keep Open
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                // TODO: Implement cancel bid package API call
                setShowCancelConfirm(false);
                toast({ variant: 'info', message: 'Cancel bid package is not yet implemented.' });
              }}
            >
              Cancel Bid Package
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to cancel this bid package? All pending invitations will be marked
          as expired. This action cannot be undone.
        </p>
      </Modal>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <Card>
      <div className="p-4 text-center">
        <p className="text-xs font-medium text-secondary-500">{label}</p>
        <p className={cn('mt-1 text-2xl font-bold', color)}>{value}</p>
      </div>
    </Card>
  );
}
