import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, useToast } from '@/components/ui';
import { ROUTES } from '@/constants/routes';
import { BidDeadlineCountdown } from '../components/BidDeadlineCountdown';
import { DeadlineExpiredModal } from '../components/DeadlineExpiredModal';
import { DraftIndicator } from '../components/DraftIndicator';
import { PORTAL_STEPS, ProgressStepper } from '../components/ProgressStepper';
import { Step1CompanyInfo } from '../components/steps/Step1CompanyInfo';
import { Step2Pricing } from '../components/steps/Step2Pricing';
import { Step3Documents } from '../components/steps/Step3Documents';
import { Step4Review } from '../components/steps/Step4Review';
import { useAutoSave } from '../hooks/useAutoSave';
import { useBidContext } from '../hooks/useBidContext';
import {
  computeGrandTotal,
  useBidFormState,
} from '../hooks/useBidFormState';
import {
  createDraft,
  getRevisionPrefill,
  listSubmissionAttachments,
  submitBid,
  updateDraft,
  type DraftPayload,
} from '../services/portalApi';
import {
  PortalApiError,
  type FormLineItem,
  type PortalFieldError,
  type StepIndex,
  type SubmissionAttachmentMeta,
} from '../types/portal';
import { prefillToHydration } from '../utils/prefill';

/**
 * Maps a server field path to the step that owns it. The validator
 * returns paths like `line_items[2].unit_price`, `total_amount`, or
 * `vendor_notes` — we route the user to the first step that can fix
 * the first error in the list.
 */
function stepForField(field: string): StepIndex {
  // Task 8.1.5: proposed_start_date lives on Step 1 alongside vendor info.
  if (field.startsWith('proposed_start_date')) return 1;
  // SoW attestation lives on Step 1 next to Project Timing.
  if (field.startsWith('sow_attested')) return 1;
  if (field.startsWith('vendor_notes')) return 3;
  if (field.startsWith('line_items') || field.startsWith('total_amount')) return 2;
  return 2;
}

/** Static server field paths → vendor-facing labels. */
const FIELD_LABELS: Record<string, string> = {
  total_amount: 'Total bid amount',
  vendor_notes: 'Notes to owner',
  proposed_start_date: 'Proposed start date',
  sow_attested_name: 'Scope of Work signature',
  line_items: 'Line items',
};

/** Per-line subfields inside `line_items[N].<sub>`. */
const LINE_SUBFIELD_LABELS: Record<string, string> = {
  quantity: 'Quantity',
  unit_price: 'Unit price',
  lump_sum_amount: 'Lump sum',
  line_total: 'Line total',
  item_type: 'Item type',
};

/**
 * Turns a raw server field path (e.g. `line_items[2].unit_price`) into a
 * vendor-readable label. Line-item paths resolve to the item's description,
 * relying on client `line_items` sharing the server's sort_order ordering.
 */
function friendlyFieldLabel(field: string, lineItems: FormLineItem[]): string {
  const staticLabel = FIELD_LABELS[field];
  if (staticLabel) return staticLabel;
  const match = field.match(/^line_items\[(\d+)\]\.(\w+)$/);
  if (match) {
    const idx = Number(match[1]);
    const sub = LINE_SUBFIELD_LABELS[match[2]] ?? match[2];
    const desc = lineItems[idx]?.description;
    return desc ? `${desc}: ${sub}` : `Line ${idx + 1}: ${sub}`;
  }
  return field;
}

export function BidFormPage() {
  const bidContext = useBidContext();
  const navigate = useNavigate();
  const { toast } = useToast();
  // Seed proposed_start_date with the package's desired_start_date —
  // calendar-invite prefill (Task 8.1.5). HYDRATE_FROM_DRAFT /
  // _PREFILL will overwrite this when an existing draft or revision
  // prefill loads.
  const form = useBidFormState(
    bidContext.bid_template,
    bidContext.bid_package.desired_start_date,
  );
  const revision = bidContext.revision_context ?? null;
  const isRevision = !!revision;
  const [previouslyUploaded, setPreviouslyUploaded] = useState<
    SubmissionAttachmentMeta[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [deadlinePassed, setDeadlinePassed] = useState(false);
  const [deadlineModalOpen, setDeadlineModalOpen] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<PortalFieldError[] | null>(null);
  // In-flight ensureSubmissionId promise — dedupes concurrent upload-
  // initiated draft creations from racing the auto-save POST.
  const creatingDraftRef = useRef<Promise<string> | null>(null);
  // Focus target for step changes (a11y): moving focus here announces the
  // new step (via aria-label) and gives keyboard users a fresh anchor.
  const stepContainerRef = useRef<HTMLDivElement>(null);

  // Hydrate on first mount. Initial path: from existing_draft if any.
  // Revision path: resume an in-progress revision draft if the backend
  // returned one, else prefill from the original submission; either way
  // load the original's attachments for the read-only "previously
  // uploaded" list. Any prefill/list failure means the revision request
  // is no longer usable → revision-inactive page.
  useEffect(() => {
    if (isRevision && revision) {
      (async () => {
        try {
          if (bidContext.existing_draft) {
            form.hydrateFromDraft(bidContext.existing_draft);
          } else {
            const pf = await getRevisionPrefill(revision.original_submission_id);
            form.hydrateFromPrefill(prefillToHydration(pf));
          }
          const atts = await listSubmissionAttachments(
            revision.original_submission_id,
          );
          setPreviouslyUploaded(atts);
        } catch {
          navigate(ROUTES.PORTAL_REVISION_INACTIVE, { replace: true });
        }
      })();
    } else if (bidContext.existing_draft) {
      form.hydrateFromDraft(bidContext.existing_draft);
    }
    // Intentionally run once on mount; context is stable within session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Deadline handling ───────────────────────────────────────────
  const handleDeadlinePassed = useCallback(() => {
    setDeadlinePassed(true);
    setDeadlineModalOpen(true);
  }, []);

  // ─── Draft payload builder ────────────────────────────────────────
  const buildDraftPayload = useCallback((): DraftPayload => {
    const { state } = form;
    return {
      vendor_notes: state.companyInfo.vendor_notes,
      proposed_start_date: state.companyInfo.proposed_start_date,
      sow_attested_name: state.companyInfo.sow_attested_name || null,
      total_amount: bidContext.bid_template.is_lump_sum
        ? state.pricing.total_amount
        : computeGrandTotal(state.pricing.line_items),
      line_items: state.pricing.line_items.map((li) => ({
        template_item_id: li.template_item_id,
        quantity: li.quantity,
        unit_price: li.unit_price,
        lump_sum_amount: li.lump_sum_amount,
      })),
      attachment_ids: form.state.attachments.map((a) => a.id),
    };
  }, [form, bidContext.bid_template.is_lump_sum]);

  const saveDraft = useCallback(async () => {
    const payload = buildDraftPayload();
    try {
      if (form.state.submissionId) {
        await updateDraft(form.state.submissionId, payload);
      } else {
        const draft = await createDraft(payload);
        form.setSubmissionId(draft.id);
      }
      form.markClean();
    } catch (err) {
      if (
        err instanceof PortalApiError &&
        err.code === 'DRAFT_CONFLICT' &&
        err.existingSubmissionId
      ) {
        // Concurrent POST race: adopt the existing draft id and retry
        // as PUT against the same payload. This is the documented
        // recovery path from the backend's UNIQUE(bid_invitation_id).
        form.setSubmissionId(err.existingSubmissionId);
        await updateDraft(err.existingSubmissionId, payload);
        form.markClean();
        return;
      }
      if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
        handleDeadlinePassed();
        // Swallow so auto-save status settles cleanly; Submit button is
        // already disabled and the modal has taken over the UX.
        return;
      }
      throw err;
    }
  }, [buildDraftPayload, form, handleDeadlinePassed]);

  // ─── ensureSubmissionId (for uploads before first save) ──────────
  const ensureSubmissionId = useCallback(async (): Promise<string> => {
    if (form.state.submissionId) return form.state.submissionId;
    if (creatingDraftRef.current) return creatingDraftRef.current;
    const p = (async () => {
      const draft = await createDraft(buildDraftPayload());
      form.setSubmissionId(draft.id);
      form.markClean();
      return draft.id;
    })();
    creatingDraftRef.current = p;
    try {
      return await p;
    } catch (err) {
      if (
        err instanceof PortalApiError &&
        err.code === 'DRAFT_CONFLICT' &&
        err.existingSubmissionId
      ) {
        form.setSubmissionId(err.existingSubmissionId);
        return err.existingSubmissionId;
      }
      throw err;
    } finally {
      creatingDraftRef.current = null;
    }
  }, [buildDraftPayload, form]);

  // ─── Auto-save wire-up ────────────────────────────────────────────
  const autoSave = useAutoSave({
    onSave: saveDraft,
    dirty: form.state.dirty,
  });

  const handleManualSave = useCallback(async () => {
    try {
      await autoSave.save();
      toast({ variant: 'success', message: 'Draft saved' });
    } catch (err) {
      if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
        handleDeadlinePassed();
        return;
      }
      toast({ variant: 'danger', message: 'Could not save draft. Please try again.' });
    }
  }, [autoSave, toast, handleDeadlinePassed]);

  // ─── Step navigation ──────────────────────────────────────────────
  const goToStep = useCallback(
    (step: StepIndex) => {
      form.setStep(step);
      // Move keyboard/SR focus into the new step (its aria-label names the
      // step), then scroll to the top for mobile UX.
      requestAnimationFrame(() => {
        stepContainerRef.current?.focus({ preventScroll: true });
        const main = document.getElementById('portal-main');
        main?.scrollTo({ top: 0, behavior: 'smooth' });
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    },
    [form],
  );

  const handleNextFromStep = useCallback(
    (current: StepIndex) => {
      form.markCompleted(current);
      goToStep((current + 1) as StepIndex);
    },
    [form, goToStep],
  );

  const handleBackFromStep = useCallback(
    (current: StepIndex) => {
      if (current <= 1) return;
      goToStep((current - 1) as StepIndex);
    },
    [goToStep],
  );

  // Stepper click — only allowed for completed steps.
  const handleStepClick = useCallback(
    (step: StepIndex) => {
      if (form.state.completedSteps.includes(step) || step === form.state.step) {
        goToStep(step);
      }
    },
    [form.state.completedSteps, form.state.step, goToStep],
  );

  // ─── Submit ───────────────────────────────────────────────────────
  const grandTotal = useMemo(() => {
    return bidContext.bid_template.is_lump_sum
      ? form.state.pricing.total_amount ?? 0
      : computeGrandTotal(form.state.pricing.line_items);
  }, [bidContext.bid_template.is_lump_sum, form.state.pricing]);

  const handleSubmit = useCallback(async () => {
    if (deadlinePassed) {
      setDeadlineModalOpen(true);
      return;
    }
    setFieldErrors(null);
    setSubmitting(true);
    try {
      // Ensure a draft exists and is up-to-date before finalizing.
      let submissionId = form.state.submissionId;
      if (!submissionId) {
        submissionId = await ensureSubmissionId();
      } else if (form.state.dirty) {
        try {
          await updateDraft(submissionId, buildDraftPayload());
          form.markClean();
        } catch (err) {
          if (
            err instanceof PortalApiError &&
            err.code === 'DRAFT_CONFLICT' &&
            err.existingSubmissionId
          ) {
            // Race-recovery as in saveDraft.
            form.setSubmissionId(err.existingSubmissionId);
            await updateDraft(err.existingSubmissionId, buildDraftPayload());
            form.markClean();
            submissionId = err.existingSubmissionId;
          } else {
            throw err;
          }
        }
      }

      const result = await submitBid(submissionId);
      toast({
        variant: 'success',
        message: isRevision
          ? 'Revised bid submitted successfully'
          : 'Bid submitted successfully',
      });
      navigate(`/bid/submitted/${result.id}`, {
        replace: true,
        state: { result, grandTotal, isRevision },
      });
    } catch (err) {
      if (
        isRevision &&
        err instanceof PortalApiError &&
        err.status === 410
      ) {
        // Revision request cancelled/expired between open and submit.
        navigate(ROUTES.PORTAL_REVISION_INACTIVE, { replace: true });
        return;
      }
      if (err instanceof PortalApiError && err.code === 'DEADLINE_PASSED') {
        handleDeadlinePassed();
      } else if (
        err instanceof PortalApiError &&
        err.code === 'VALIDATION_FAILED' &&
        err.validationErrors &&
        err.validationErrors.length > 0
      ) {
        setFieldErrors(err.validationErrors);
        const firstStep = stepForField(err.validationErrors[0].field);
        goToStep(firstStep);
        toast({
          variant: 'danger',
          message: 'Please fix the highlighted issues before submitting.',
        });
      } else if (err instanceof PortalApiError && err.code === 'ALREADY_SUBMITTED') {
        toast({
          variant: 'danger',
          message: 'This bid has already been submitted.',
        });
      } else {
        // eslint-disable-next-line no-console
        console.error('[BidFormPage] submit failed', err);
        const detail =
          err instanceof PortalApiError
            ? err.message
            : 'Submission failed. Please try again or contact support.';
        toast({ variant: 'danger', message: detail });
      }
    } finally {
      setSubmitting(false);
    }
  }, [
    buildDraftPayload,
    deadlinePassed,
    ensureSubmissionId,
    form,
    goToStep,
    grandTotal,
    handleDeadlinePassed,
    isRevision,
    navigate,
    toast,
  ]);

  // ─── Render ───────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-secondary-900 sm:text-2xl">
            Submit Your Bid
          </h1>
          <p className="mt-1 text-sm text-secondary-600">
            Round {bidContext.bid_package.round_number} · {bidContext.task.trade_name}
          </p>
        </div>
        <div className="flex flex-col items-stretch gap-3 sm:items-end">
          <BidDeadlineCountdown
            deadline={
              isRevision && revision
                ? revision.revision_deadline
                : bidContext.bid_package.deadline
            }
            label={isRevision ? 'Revision deadline' : 'Bid deadline'}
          />
          <DraftIndicator
            status={autoSave.status}
            lastSavedAt={autoSave.lastSavedAt}
            dirty={form.state.dirty}
          />
        </div>
      </div>

      {isRevision && revision && (
        <div className="mt-6">
          <Alert
            variant="warning"
            title="You are submitting a revision. Your original bid is preserved."
          >
            <p className="mt-1 text-xs font-medium tracking-wide text-warning-700 uppercase">
              Note from the project manager
            </p>
            <p className="mt-1 whitespace-pre-wrap">{revision.pm_note}</p>
          </Alert>
        </div>
      )}

      <div className="mt-6">
        <ProgressStepper
          currentStep={form.state.step}
          completedSteps={form.state.completedSteps}
          onStepClick={handleStepClick}
        />
      </div>

      {fieldErrors && fieldErrors.length > 0 && (
        <div className="mt-6">
          <Alert variant="danger" title="Please fix the following before submitting">
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {fieldErrors.map((e, idx) => (
                <li key={`${e.field}-${idx}`}>
                  <span className="font-medium">
                    {friendlyFieldLabel(e.field, form.state.pricing.line_items)}:
                  </span>{' '}
                  {e.message}
                </li>
              ))}
            </ul>
          </Alert>
        </div>
      )}

      <div
        ref={stepContainerRef}
        tabIndex={-1}
        aria-label={`Step ${form.state.step}: ${
          PORTAL_STEPS.find((s) => s.index === form.state.step)?.label ?? ''
        }`}
        className="mt-6 focus:outline-none"
      >
        {form.state.step === 1 && (
          <Step1CompanyInfo
            onNext={() => handleNextFromStep(1)}
            onSaveDraft={handleManualSave}
            proposedStartDate={form.state.companyInfo.proposed_start_date}
            onUpdateProposedStartDate={form.updateProposedStartDate}
            sowAttestedName={form.state.companyInfo.sow_attested_name}
            onUpdateSowAttestation={form.updateSowAttestation}
          />
        )}
        {form.state.step === 2 && (
          <Step2Pricing
            state={form.state}
            onSetLumpTotal={form.setLumpTotal}
            onUpdateLineItem={form.updateLineItem}
            onNext={() => handleNextFromStep(2)}
            onBack={() => handleBackFromStep(2)}
            onSaveDraft={handleManualSave}
          />
        )}
        {form.state.step === 3 && (
          <Step3Documents
            state={form.state}
            onUpdateNotes={form.updateCompanyNotes}
            onAddAttachment={form.addAttachment}
            onRemoveAttachment={form.removeAttachment}
            onNext={() => handleNextFromStep(3)}
            onBack={() => handleBackFromStep(3)}
            onSaveDraft={handleManualSave}
            ensureSubmissionId={ensureSubmissionId}
            onDeadlinePassed={handleDeadlinePassed}
            disabled={deadlinePassed}
            previouslyUploaded={isRevision ? previouslyUploaded : undefined}
          />
        )}
        {form.state.step === 4 && (
          <Step4Review
            state={form.state}
            onEdit={goToStep}
            onBack={() => handleBackFromStep(4)}
            onSaveDraft={handleManualSave}
            onSubmit={handleSubmit}
            submitting={submitting}
            disabled={deadlinePassed}
            isRevision={isRevision}
          />
        )}
      </div>

      <DeadlineExpiredModal
        open={deadlineModalOpen}
        onClose={() => setDeadlineModalOpen(false)}
      />
    </div>
  );
}
