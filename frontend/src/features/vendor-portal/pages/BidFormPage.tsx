import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui';
import { BidDeadlineCountdown } from '../components/BidDeadlineCountdown';
import { DraftIndicator } from '../components/DraftIndicator';
import { ProgressStepper } from '../components/ProgressStepper';
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
  submitBid,
  updateDraft,
  type DraftPayload,
} from '../services/portalApi';
import type { StepIndex } from '../types/portal';

export function BidFormPage() {
  const bidContext = useBidContext();
  const navigate = useNavigate();
  const { toast } = useToast();
  const form = useBidFormState(bidContext.bid_template);
  const [submitting, setSubmitting] = useState(false);

  // Hydrate from existing draft on first mount if backend provided one.
  useEffect(() => {
    if (bidContext.existing_draft) {
      form.hydrateFromDraft(bidContext.existing_draft);
    }
    // Intentionally run once on mount; context is stable within session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Draft payload builder ────────────────────────────────────────
  const buildDraftPayload = useCallback((): DraftPayload => {
    const { state } = form;
    return {
      vendor_notes: state.companyInfo.vendor_notes,
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
    if (form.state.submissionId) {
      await updateDraft(form.state.submissionId, payload);
    } else {
      const draft = await createDraft(payload);
      form.setSubmissionId(draft.id);
    }
    form.markClean();
  }, [buildDraftPayload, form]);

  // ─── Auto-save wire-up ────────────────────────────────────────────
  // NOTE: Production interval is 2 min (default). For manual verification,
  // temporarily set intervalMs to e.g. 15_000.
  const autoSave = useAutoSave({
    onSave: saveDraft,
    dirty: form.state.dirty,
  });

  const handleManualSave = useCallback(async () => {
    try {
      await autoSave.save();
      toast({ variant: 'success', message: 'Draft saved' });
    } catch {
      toast({ variant: 'danger', message: 'Could not save draft. Please try again.' });
    }
  }, [autoSave, toast]);

  // ─── Step navigation ──────────────────────────────────────────────
  const goToStep = useCallback(
    (step: StepIndex) => {
      form.setStep(step);
      // Focus main heading / top for a11y + mobile UX.
      requestAnimationFrame(() => {
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
    setSubmitting(true);
    try {
      // Ensure a draft exists first — mirrors real flow where submit
      // finalizes an existing draft.
      let submissionId = form.state.submissionId;
      if (!submissionId) {
        const draft = await createDraft(buildDraftPayload());
        form.setSubmissionId(draft.id);
        submissionId = draft.id;
      } else if (form.state.dirty) {
        await updateDraft(submissionId, buildDraftPayload());
        form.markClean();
      }

      const result = await submitBid(submissionId);
      toast({ variant: 'success', message: 'Bid submitted successfully' });
      navigate(`/bid/submitted/${result.id}`, {
        replace: true,
        state: { result, grandTotal },
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[BidFormPage] submit failed', err);
      toast({
        variant: 'danger',
        message: 'Submission failed. Please try again or contact support.',
      });
    } finally {
      setSubmitting(false);
    }
  }, [
    buildDraftPayload,
    form,
    grandTotal,
    navigate,
    toast,
  ]);

  // ─── Render ───────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-secondary-900 sm:text-2xl">
            Submit Your Bid
          </h1>
          <p className="mt-1 text-sm text-secondary-600">
            Round {bidContext.bid_package.round_number} · {bidContext.task.trade_name}
          </p>
        </div>
        <DraftIndicator
          status={autoSave.status}
          lastSavedAt={autoSave.lastSavedAt}
          dirty={form.state.dirty}
        />
      </div>

      <div className="mt-4 sm:hidden">
        <BidDeadlineCountdown deadline={bidContext.bid_package.deadline} />
      </div>

      <div className="mt-6">
        <ProgressStepper
          currentStep={form.state.step}
          completedSteps={form.state.completedSteps}
          onStepClick={handleStepClick}
        />
      </div>

      <div className="mt-6">
        {form.state.step === 1 && (
          <Step1CompanyInfo
            onNext={() => handleNextFromStep(1)}
            onSaveDraft={handleManualSave}
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
          />
        )}
      </div>
    </div>
  );
}
