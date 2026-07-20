import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ChevronDown, FileText } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { useBidPackageDetail } from '@/features/bids/hooks/useBidPackageDetail';
import { useTask } from '@/features/tasks/hooks/useTask';
import { useRevisionRequests } from '@/features/bids/hooks/useRevisionRequests';
import { useBidPackageEmailLog } from '@/features/bids/hooks/useBidPackageEmailLog';
import { useResendBidLink } from '@/features/bids/hooks/useResendBidLink';
import { useCloseBidding } from '@/features/bids/hooks/useCloseBidding';
import { useUpdateInvitationStatus } from '@/features/bids/hooks/useUpdateInvitationStatus';
import { useCountdown } from '@/features/bids/hooks/useCountdown';
import { InvitationsTable } from '@/features/bids/components/InvitationsTable';
import { BidSubmissionDetailModal } from '@/features/bids/components/BidSubmissionDetailModal';
import { RequestRevisionModal } from '@/features/bids/components/RequestRevisionModal';
import { CancelRevisionDialog } from '@/features/bids/components/CancelRevisionDialog';
import { EmailLogTable } from '@/features/bids/components/EmailLogTable';
import { SubmissionStatusPie } from '@/features/bids/components/SubmissionStatusPie';
import { formatDateOnly } from '@/lib/format';
import { cn } from '@/utils/cn';
import type { BidInvitation, BidRevisionRequest } from '@/features/bids/types';

export function BidPackageDetailPage() {
  const { id: projectId, taskId, bidPackageId } = useParams<{
    id: string;
    taskId: string;
    bidPackageId: string;
  }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: bp, isLoading, error } = useBidPackageDetail(bidPackageId!);
  const { data: task } = useTask(projectId!, taskId!);
  const { data: revisionRequests } = useRevisionRequests(bidPackageId!);
  const { remaining, isPassed } = useCountdown(bp?.deadline ?? '');

  // Most-recent non-cancelled revision request per invitation. The list is
  // sorted newest-first, so the first non-cancelled hit per invitation wins.
  const revisionByInvitationId = useMemo(() => {
    const map = new Map<string, BidRevisionRequest>();
    for (const req of revisionRequests ?? []) {
      if (req.status === 'cancelled') continue;
      if (!map.has(req.bid_invitation_id)) {
        map.set(req.bid_invitation_id, req);
      }
    }
    return map;
  }, [revisionRequests]);

  // Email log — lazy loaded
  const [showEmailLog, setShowEmailLog] = useState(false);
  const { data: emailLog, isLoading: emailLogLoading } = useBidPackageEmailLog(
    bidPackageId!,
    showEmailLog,
  );

  // Mutations
  const resendBidLinkMutation = useResendBidLink(bidPackageId!);
  const statusMutation = useUpdateInvitationStatus(bidPackageId!);
  const closeBiddingMutation = useCloseBidding(bidPackageId!, taskId!);

  const [resendingId, setResendingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [declineConfirmId, setDeclineConfirmId] = useState<string | null>(null);
  const [viewSubmissionId, setViewSubmissionId] = useState<string | null>(null);
  const [expandedInvitationId, setExpandedInvitationId] = useState<string | null>(
    null,
  );
  const [requestRevisionFor, setRequestRevisionFor] =
    useState<BidInvitation | null>(null);
  const [cancelRevision, setCancelRevision] = useState<{
    request: BidRevisionRequest;
    invitation: BidInvitation;
  } | null>(null);

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

  const handleConfirmClose = () => {
    closeBiddingMutation.mutate(undefined, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Bidding closed. The package is now under evaluation.' });
        setShowCloseConfirm(false);
      },
      onError: (err) => {
        toast({
          variant: 'danger',
          message: (err as { message?: string })?.message || 'Failed to close bidding.',
        });
      },
    });
  };

  const handleConfirmDecline = () => {
    if (!declineConfirmId) return;
    const invitationId = declineConfirmId;
    setDeclineConfirmId(null);
    setUpdatingId(invitationId);
    statusMutation.mutate(
      { invitationId, status: 'declined' },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Invitation marked as declined.' });
          setUpdatingId(null);
        },
        onError: (err) => {
          toast({
            variant: 'danger',
            message: (err as { message?: string })?.message || 'Failed to mark declined.',
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
            <ArrowLeft className="h-5 w-5" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
              {bp.task_name} (Round {bp.round_number})
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
          {/* Task 8.3 gate: competitive + ≥1 submitted bid; status/deadline never gate. */}
          {task?.bid_type === 'competitive' &&
            bp.submitted_bids.length > 0 &&
            bp.status !== 'cancelled' && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  navigate(
                    `/projects/${projectId}/tasks/${taskId}/bid-packages/${bidPackageId}/compare`,
                  )
                }
              >
                Compare Bids
              </Button>
            )}
          {bp.status === 'open' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCloseConfirm(true)}
            >
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
          value={summary.sent + summary.opened + summary.pending_send}
          color="text-info-600"
        />
        <SummaryCard
          label="Declined / Expired"
          value={summary.declined + summary.expired}
          color="text-secondary-500"
        />
        {/* Only shown when sends failed, so the normal flow keeps four cards. */}
        {summary.send_failed > 0 && (
          <SummaryCard
            label="Failed to Send"
            value={summary.send_failed}
            color="text-danger-600"
          />
        )}
      </div>

      {/* Submission Status Pie */}
      {summary.total > 0 && (
        <div className="mx-auto max-w-xl">
          <SubmissionStatusPie summary={summary} />
        </div>
      )}

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

      {/* Desired Start Date (Task 8.1.5) */}
      {bp.desired_start_date && (
        <div className="rounded-lg border border-secondary-200 bg-white p-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-secondary-500">
            Desired Start Date
          </h3>
          <p className="text-sm font-semibold text-secondary-900">
            {formatDateOnly(bp.desired_start_date)}
          </p>
          <p className="mt-1 text-xs text-secondary-500">
            Target start communicated to vendors. Vendors&apos; proposed start
            dates are shown on each submitted bid.
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
            onMarkDeclined={setDeclineConfirmId}
            onViewBid={setViewSubmissionId}
            resendingId={resendingId}
            updatingId={updatingId}
            revisionByInvitationId={revisionByInvitationId}
            expandedInvitationId={expandedInvitationId}
            onToggleExpand={(id) =>
              setExpandedInvitationId((cur) => (cur === id ? null : id))
            }
            onRequestRevision={setRequestRevisionFor}
            onCancelRevision={(request, invitation) =>
              setCancelRevision({ request, invitation })
            }
            bidPackageOpen={bp.status === 'open'}
          />
        </div>
      </Card>

      {/* Bid Amount Comparison moved to /compare route (Task 8.3). */}

      {/* Documents */}
      {bp.documents.length > 0 && (
        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Attached Documents</h3>
            <ul className="space-y-1">
              {bp.documents.map((doc) => (
                <li key={doc.id} className="flex items-center gap-2 text-sm text-secondary-700">
                  <FileText className="h-4 w-4 shrink-0 text-secondary-400" aria-hidden="true" />
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
            <ChevronDown
              className={cn(
                'h-4 w-4 text-secondary-400 transition-transform',
                showEmailLog && 'rotate-180',
              )}
              aria-hidden="true"
            />
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

      {/* View Bid Submission Modal */}
      <BidSubmissionDetailModal
        submissionId={viewSubmissionId}
        isOpen={!!viewSubmissionId}
        onClose={() => setViewSubmissionId(null)}
      />

      {/* Request Revision Modal */}
      {requestRevisionFor && (
        <RequestRevisionModal
          isOpen={!!requestRevisionFor}
          onClose={() => setRequestRevisionFor(null)}
          invitation={requestRevisionFor}
          bidPackageId={bidPackageId!}
        />
      )}

      {/* Cancel Revision Confirmation */}
      {cancelRevision && (
        <CancelRevisionDialog
          isOpen={!!cancelRevision}
          onClose={() => setCancelRevision(null)}
          revisionRequestId={cancelRevision.request.id}
          vendorName={cancelRevision.invitation.vendor_company_name ?? 'The vendor'}
          bidPackageId={bidPackageId!}
        />
      )}

      {/* Decline Confirmation Modal */}
      <Modal
        isOpen={!!declineConfirmId}
        onClose={() => setDeclineConfirmId(null)}
        title="Mark as Declined"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeclineConfirmId(null)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleConfirmDecline}>
              Mark Declined
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Mark this vendor as declined? Their magic link will be revoked and they will no longer
          be able to access the bid portal. This cannot be undone.
        </p>
      </Modal>

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

      {/* Close Bidding Confirmation Modal */}
      <Modal
        isOpen={showCloseConfirm}
        onClose={() => {
          if (!closeBiddingMutation.isPending) setShowCloseConfirm(false);
        }}
        title="Close bidding"
        size="sm"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setShowCloseConfirm(false)}
              disabled={closeBiddingMutation.isPending}
            >
              Keep open
            </Button>
            <Button
              variant="primary"
              onClick={handleConfirmClose}
              isLoading={closeBiddingMutation.isPending}
            >
              Close bidding
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          This stops new bids immediately and moves the package to evaluation.{' '}
          <strong>
            {summary.total - summary.submitted} of {summary.total}
          </strong>{' '}
          invited vendor{summary.total - summary.submitted === 1 ? '' : 's'} have not submitted yet.
          Vendors with an in-flight revision request can still submit until their revision deadline.
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
