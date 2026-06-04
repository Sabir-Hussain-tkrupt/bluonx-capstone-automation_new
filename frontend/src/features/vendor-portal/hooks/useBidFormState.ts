import { useCallback, useReducer } from 'react';
import type {
  BidDraft,
  BidFormState,
  FormAttachment,
  FormLineItem,
  PortalBidTemplate,
  StepIndex,
} from '../types/portal';

// ─── Action types ──────────────────────────────────────────────────

type Action =
  | { type: 'SET_STEP'; step: StepIndex }
  | { type: 'MARK_COMPLETED'; step: StepIndex }
  | { type: 'UPDATE_COMPANY_NOTES'; value: string }
  | { type: 'UPDATE_PROPOSED_START_DATE'; value: string | null }
  | { type: 'SET_LUMP_TOTAL'; value: number | null }
  | {
      type: 'UPDATE_LINE_ITEM';
      template_item_id: string;
      patch: Partial<Pick<FormLineItem, 'quantity' | 'unit_price' | 'lump_sum_amount'>>;
    }
  | { type: 'ADD_ATTACHMENT'; attachment: FormAttachment }
  | { type: 'REMOVE_ATTACHMENT'; id: string }
  | { type: 'SET_SUBMISSION_ID'; id: string }
  | { type: 'HYDRATE_FROM_DRAFT'; draft: BidDraft }
  | { type: 'HYDRATE_FROM_PREFILL'; prefill: PrefillHydration }
  | { type: 'MARK_CLEAN' };

/**
 * Revision prefill, decimals already parsed to numbers by the caller.
 * Unlike HYDRATE_FROM_DRAFT this does NOT set submissionId — the revised
 * bid is a brand-new submission row created on first save/submit — and
 * leaves the form dirty so it gets persisted.
 */
export interface PrefillHydration {
  vendor_notes: string;
  total_amount: number | null;
  /** Vendor's prior proposed start date (Task 8.1.5). */
  proposed_start_date: string | null;
  line_items: Array<{
    template_item_id: string;
    quantity: number | null;
    unit_price: number | null;
    lump_sum_amount: number | null;
  }>;
}

// ─── Initial state from template ────────────────────────────────────

export function buildInitialFormState(
  template: PortalBidTemplate,
  initialProposedStartDate: string | null = null,
): BidFormState {
  const line_items: FormLineItem[] = template.is_lump_sum
    ? []
    : [...template.items]
        .sort((a, b) => a.sort_order - b.sort_order)
        .map((tpl) => ({
          template_item_id: tpl.id,
          description: tpl.description,
          item_type: tpl.item_type,
          unit_of_measure: tpl.unit_of_measure,
          sort_order: tpl.sort_order,
          quantity: null,
          unit_price: null,
          lump_sum_amount: null,
        }));

  return {
    step: 1,
    completedSteps: [],
    dirty: false,
    // Task 8.1.5 "calendar-invite" prefill: the vendor's proposed date
    // starts at the PM's desired date (if any); the vendor can edit it.
    companyInfo: {
      vendor_notes: '',
      proposed_start_date: initialProposedStartDate,
    },
    pricing: {
      total_amount: null,
      line_items,
    },
    attachments: [],
    submissionId: null,
  };
}

// ─── Pure line-total helper ────────────────────────────────────────

export function computeLineTotal(item: FormLineItem): number {
  if (item.item_type === 'lump_sum') {
    return Number(item.lump_sum_amount ?? 0);
  }
  const q = Number(item.quantity ?? 0);
  const p = Number(item.unit_price ?? 0);
  return q * p;
}

export function computeGrandTotal(items: FormLineItem[]): number {
  return items.reduce((sum, it) => sum + computeLineTotal(it), 0);
}

// ─── Reducer ───────────────────────────────────────────────────────

function reducer(state: BidFormState, action: Action): BidFormState {
  switch (action.type) {
    case 'SET_STEP':
      return { ...state, step: action.step };

    case 'MARK_COMPLETED': {
      if (state.completedSteps.includes(action.step)) return state;
      return { ...state, completedSteps: [...state.completedSteps, action.step] };
    }

    case 'UPDATE_COMPANY_NOTES':
      return {
        ...state,
        dirty: true,
        companyInfo: { ...state.companyInfo, vendor_notes: action.value },
      };

    case 'UPDATE_PROPOSED_START_DATE':
      return {
        ...state,
        dirty: true,
        companyInfo: {
          ...state.companyInfo,
          proposed_start_date: action.value,
        },
      };

    case 'SET_LUMP_TOTAL':
      return {
        ...state,
        dirty: true,
        pricing: { ...state.pricing, total_amount: action.value },
      };

    case 'UPDATE_LINE_ITEM': {
      const nextItems = state.pricing.line_items.map((it) =>
        it.template_item_id === action.template_item_id ? { ...it, ...action.patch } : it,
      );
      return {
        ...state,
        dirty: true,
        pricing: { ...state.pricing, line_items: nextItems },
      };
    }

    case 'ADD_ATTACHMENT':
      return {
        ...state,
        dirty: true,
        attachments: [...state.attachments, action.attachment],
      };

    case 'REMOVE_ATTACHMENT':
      return {
        ...state,
        dirty: true,
        attachments: state.attachments.filter((a) => a.id !== action.id),
      };

    case 'SET_SUBMISSION_ID':
      return { ...state, submissionId: action.id };

    case 'HYDRATE_FROM_DRAFT': {
      const lineItems = state.pricing.line_items.map((it) => {
        const match = action.draft.line_items.find(
          (d) => d.template_item_id === it.template_item_id,
        );
        if (!match) return it;
        return {
          ...it,
          quantity: match.quantity,
          unit_price: match.unit_price,
          lump_sum_amount: match.lump_sum_amount,
        };
      });
      return {
        ...state,
        submissionId: action.draft.id,
        dirty: false,
        companyInfo: {
          vendor_notes: action.draft.vendor_notes,
          proposed_start_date: action.draft.proposed_start_date,
        },
        pricing: { total_amount: action.draft.total_amount, line_items: lineItems },
      };
    }

    case 'HYDRATE_FROM_PREFILL': {
      const lineItems = state.pricing.line_items.map((it) => {
        const match = action.prefill.line_items.find(
          (d) => d.template_item_id === it.template_item_id,
        );
        if (!match) return it;
        return {
          ...it,
          quantity: match.quantity,
          unit_price: match.unit_price,
          lump_sum_amount: match.lump_sum_amount,
        };
      });
      return {
        ...state,
        // submissionId intentionally untouched (stays null → a fresh
        // revision draft is created on first save/submit).
        dirty: true,
        companyInfo: {
          vendor_notes: action.prefill.vendor_notes,
          proposed_start_date: action.prefill.proposed_start_date,
        },
        pricing: { total_amount: action.prefill.total_amount, line_items: lineItems },
      };
    }

    case 'MARK_CLEAN':
      return { ...state, dirty: false };

    default:
      return state;
  }
}

// ─── Hook ──────────────────────────────────────────────────────────

export interface UseBidFormStateResult {
  state: BidFormState;
  setStep: (step: StepIndex) => void;
  markCompleted: (step: StepIndex) => void;
  updateCompanyNotes: (value: string) => void;
  updateProposedStartDate: (value: string | null) => void;
  setLumpTotal: (value: number | null) => void;
  updateLineItem: (
    template_item_id: string,
    patch: Partial<Pick<FormLineItem, 'quantity' | 'unit_price' | 'lump_sum_amount'>>,
  ) => void;
  addAttachment: (attachment: FormAttachment) => void;
  removeAttachment: (id: string) => void;
  setSubmissionId: (id: string) => void;
  hydrateFromDraft: (draft: BidDraft) => void;
  hydrateFromPrefill: (prefill: PrefillHydration) => void;
  markClean: () => void;
}

export function useBidFormState(
  template: PortalBidTemplate,
  initialProposedStartDate: string | null = null,
): UseBidFormStateResult {
  const [state, dispatch] = useReducer(
    reducer,
    undefined,
    () => buildInitialFormState(template, initialProposedStartDate),
  );

  return {
    state,
    setStep: useCallback((step) => dispatch({ type: 'SET_STEP', step }), []),
    markCompleted: useCallback((step) => dispatch({ type: 'MARK_COMPLETED', step }), []),
    updateCompanyNotes: useCallback(
      (value) => dispatch({ type: 'UPDATE_COMPANY_NOTES', value }),
      [],
    ),
    updateProposedStartDate: useCallback(
      (value) => dispatch({ type: 'UPDATE_PROPOSED_START_DATE', value }),
      [],
    ),
    setLumpTotal: useCallback(
      (value) => dispatch({ type: 'SET_LUMP_TOTAL', value }),
      [],
    ),
    updateLineItem: useCallback(
      (template_item_id, patch) =>
        dispatch({ type: 'UPDATE_LINE_ITEM', template_item_id, patch }),
      [],
    ),
    addAttachment: useCallback(
      (attachment) => dispatch({ type: 'ADD_ATTACHMENT', attachment }),
      [],
    ),
    removeAttachment: useCallback(
      (id) => dispatch({ type: 'REMOVE_ATTACHMENT', id }),
      [],
    ),
    setSubmissionId: useCallback(
      (id) => dispatch({ type: 'SET_SUBMISSION_ID', id }),
      [],
    ),
    hydrateFromDraft: useCallback(
      (draft) => dispatch({ type: 'HYDRATE_FROM_DRAFT', draft }),
      [],
    ),
    hydrateFromPrefill: useCallback(
      (prefill) => dispatch({ type: 'HYDRATE_FROM_PREFILL', prefill }),
      [],
    ),
    markClean: useCallback(() => dispatch({ type: 'MARK_CLEAN' }), []),
  };
}
