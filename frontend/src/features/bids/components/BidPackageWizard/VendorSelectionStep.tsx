import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { useQualifiedVendors } from '@/features/bids/hooks/useQualifiedVendors';
import type { QualifiedVendor, VendorSelection } from '@/features/bids/types';
import { cn } from '@/utils/cn';

interface VendorSelectionStepProps {
  taskId: string;
  data: { vendorSelections: VendorSelection[] };
  onUpdate: (selections: VendorSelection[]) => void;
  onNext: () => void;
  onBack: () => void;
}

type SortKey = 'distance' | 'company' | 'capacity';

function formatDate(value: string | null): string {
  if (!value) return '\u2014';
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function VendorSelectionStep({
  taskId,
  data,
  onUpdate,
  onNext,
  onBack,
}: VendorSelectionStepProps) {
  const { data: vendorData, isLoading, error } = useQualifiedVendors(taskId);

  // Selected vendor map: vendorId → contactId
  const [selected, setSelected] = useState<Map<string, string>>(new Map());
  // Expanded vendor row
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // Sort
  const [sortKey, setSortKey] = useState<SortKey>('distance');
  // Show disqualified
  const [showDisqualified, setShowDisqualified] = useState(false);
  // Override confirm modal
  const [overrideVendor, setOverrideVendor] = useState<QualifiedVendor | null>(null);
  // Validation error
  const [validationError, setValidationError] = useState('');

  // Initialize selections from qualified vendors on first load
  useEffect(() => {
    if (!vendorData) return;

    // If we already have selections from a previous visit (going back), restore them
    if (data.vendorSelections.length > 0) {
      const map = new Map<string, string>();
      for (const s of data.vendorSelections) {
        map.set(s.vendor_id, s.vendor_contact_id);
      }
      setSelected(map);
      return;
    }

    // Otherwise pre-check all qualified vendors with their primary contact
    const map = new Map<string, string>();
    for (const v of vendorData.qualified_vendors) {
      if (v.primary_contact) {
        map.set(v.vendor_id, v.primary_contact.id);
      }
    }
    setSelected(map);
  }, [vendorData, data.vendorSelections]);

  const qualified = vendorData?.qualified_vendors ?? [];
  const disqualified = vendorData?.disqualified_vendors ?? [];

  // Sort qualified vendors
  const sortedQualified = useMemo(() => {
    const list = [...qualified];
    list.sort((a, b) => {
      switch (sortKey) {
        case 'distance':
          return (a.distance_miles ?? 999) - (b.distance_miles ?? 999);
        case 'company':
          return a.company_name.localeCompare(b.company_name);
        case 'capacity':
          return (b.available_capacity ?? 0) - (a.available_capacity ?? 0);
        default:
          return 0;
      }
    });
    return list;
  }, [qualified, sortKey]);

  const toggleVendor = (vendor: QualifiedVendor) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(vendor.vendor_id)) {
        next.delete(vendor.vendor_id);
      } else if (vendor.primary_contact) {
        next.set(vendor.vendor_id, vendor.primary_contact.id);
      }
      return next;
    });
    setValidationError('');
  };

  const changeContact = (vendorId: string, contactId: string) => {
    setSelected((prev) => {
      const next = new Map(prev);
      next.set(vendorId, contactId);
      return next;
    });
  };

  const selectAll = () => {
    const map = new Map(selected);
    for (const v of qualified) {
      if (v.primary_contact && !map.has(v.vendor_id)) {
        map.set(v.vendor_id, v.primary_contact.id);
      }
    }
    setSelected(map);
    setValidationError('');
  };

  const deselectAll = () => {
    // Only deselect qualified vendors (keep any overridden disqualified ones)
    const qualifiedIds = new Set(qualified.map((v) => v.vendor_id));
    setSelected((prev) => {
      const next = new Map(prev);
      for (const id of qualifiedIds) {
        next.delete(id);
      }
      return next;
    });
  };

  const handleOverrideConfirm = () => {
    if (overrideVendor?.primary_contact) {
      setSelected((prev) => {
        const next = new Map(prev);
        next.set(overrideVendor.vendor_id, overrideVendor.primary_contact!.id);
        return next;
      });
    }
    setOverrideVendor(null);
    setValidationError('');
  };

  const handleNext = () => {
    if (selected.size === 0) {
      setValidationError('Select at least one vendor to continue.');
      return;
    }
    // Convert map to array and propagate up
    const selections: VendorSelection[] = Array.from(selected.entries()).map(
      ([vendor_id, vendor_contact_id]) => ({ vendor_id, vendor_contact_id }),
    );
    onUpdate(selections);
    onNext();
  };

  const allQualifiedSelected = qualified.every(
    (v) => !v.primary_contact || selected.has(v.vendor_id),
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton height="40px" />
        <Skeleton height="300px" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="danger" title="Failed to load vendors">
        Could not fetch qualified vendors. Please try again.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Warnings from filtering */}
      {vendorData?.warnings && vendorData.warnings.length > 0 && (
        <Alert variant="warning" title="Vendor filtering warnings">
          <ul className="list-disc pl-4">
            {vendorData.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}

      {/* Qualified Vendors */}
      <Card>
        <div className="p-6">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-secondary-900">
                Qualified Vendors ({qualified.length})
              </h3>
              <p className="mt-0.5 text-xs text-secondary-500">
                {selected.size} of {qualified.length + disqualified.length} selected
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* Sort */}
              <label className="flex items-center gap-1.5 text-xs text-secondary-500">
                Sort:
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  className="rounded border border-secondary-300 px-2 py-1 text-xs"
                >
                  <option value="distance">Distance</option>
                  <option value="company">Company Name</option>
                  <option value="capacity">Capacity</option>
                </select>
              </label>
              {/* Select / Deselect All */}
              <button
                type="button"
                onClick={allQualifiedSelected ? deselectAll : selectAll}
                className="text-xs font-medium text-primary-600 hover:text-primary-700"
              >
                {allQualifiedSelected ? 'Deselect All' : 'Select All'}
              </button>
            </div>
          </div>

          {validationError && (
            <Alert variant="danger" className="mb-4">
              {validationError}
            </Alert>
          )}

          {qualified.length === 0 ? (
            <p className="text-sm text-secondary-500">No qualified vendors found for this task.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-secondary-200 text-left text-xs font-medium uppercase tracking-wider text-secondary-500">
                    <th className="w-10 pb-3 pr-2" />
                    <th className="pb-3 pr-4">Company</th>
                    <th className="hidden pb-3 pr-4 md:table-cell">Contact</th>
                    <th className="hidden pb-3 pr-4 lg:table-cell">Email</th>
                    <th className="pb-3 pr-4 text-right">Distance</th>
                    <th className="hidden pb-3 pr-4 md:table-cell">Insurance</th>
                    <th className="hidden pb-3 pr-4 text-center lg:table-cell">Capacity</th>
                    <th className="pb-3 text-center">Flags</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-secondary-100">
                  {sortedQualified.map((vendor) => (
                    <VendorRow
                      key={vendor.vendor_id}
                      vendor={vendor}
                      isSelected={selected.has(vendor.vendor_id)}
                      isExpanded={expandedId === vendor.vendor_id}
                      selectedContactId={selected.get(vendor.vendor_id)}
                      onToggle={() => toggleVendor(vendor)}
                      onExpand={() =>
                        setExpandedId(
                          expandedId === vendor.vendor_id ? null : vendor.vendor_id,
                        )
                      }
                      onChangeContact={(contactId) =>
                        changeContact(vendor.vendor_id, contactId)
                      }
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* Disqualified Vendors */}
      {disqualified.length > 0 && (
        <Card>
          <div className="p-6">
            <button
              type="button"
              onClick={() => setShowDisqualified(!showDisqualified)}
              className="flex w-full items-center justify-between text-left"
            >
              <h3 className="text-sm font-semibold text-secondary-900">
                Show {disqualified.length} disqualified vendor
                {disqualified.length !== 1 ? 's' : ''}
              </h3>
              <ChevronDown
                className={cn(
                  'h-4 w-4 text-secondary-400 transition-transform',
                  showDisqualified && 'rotate-180',
                )}
                aria-hidden="true"
              />
            </button>

            {showDisqualified && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-secondary-200 text-left text-xs font-medium uppercase tracking-wider text-secondary-500">
                      <th className="w-10 pb-3 pr-2" />
                      <th className="pb-3 pr-4">Company</th>
                      <th className="hidden pb-3 pr-4 md:table-cell">Contact</th>
                      <th className="pb-3 pr-4">Reasons</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-secondary-100">
                    {disqualified.map((vendor) => (
                      <tr key={vendor.vendor_id}>
                        <td className="py-3 pr-2">
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-secondary-300 accent-primary-600"
                            checked={selected.has(vendor.vendor_id)}
                            onChange={() => {
                              if (selected.has(vendor.vendor_id)) {
                                setSelected((prev) => {
                                  const next = new Map(prev);
                                  next.delete(vendor.vendor_id);
                                  return next;
                                });
                              } else {
                                setOverrideVendor(vendor);
                              }
                            }}
                          />
                        </td>
                        <td className="py-3 pr-4 font-medium text-secondary-900">
                          {vendor.company_name}
                        </td>
                        <td className="hidden py-3 pr-4 md:table-cell">
                          {vendor.primary_contact?.full_name ?? '\u2014'}
                        </td>
                        <td className="py-3 pr-4">
                          <div className="flex flex-wrap gap-1">
                            {vendor.disqualification_reasons.map((reason, i) => (
                              <span
                                key={i}
                                className="inline-flex rounded-full bg-danger-100 px-2 py-0.5 text-xs font-medium text-danger-700"
                              >
                                {reason.replace(/_/g, ' ')}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Override Confirmation Modal */}
      <Modal
        isOpen={!!overrideVendor}
        onClose={() => setOverrideVendor(null)}
        title="Include Disqualified Vendor?"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOverrideVendor(null)}>
              Cancel
            </Button>
            <Button variant="warning" onClick={handleOverrideConfirm}>
              Include Anyway
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          <strong>{overrideVendor?.company_name}</strong> was disqualified for:
        </p>
        <ul className="mt-2 list-disc pl-5 text-sm text-secondary-600">
          {overrideVendor?.disqualification_reasons.map((r, i) => (
            <li key={i}>{r.replace(/_/g, ' ')}</li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-secondary-600">
          Are you sure you want to include this vendor in the bid package?
        </p>
      </Modal>

      {/* Footer */}
      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button onClick={handleNext}>Next: Review & Send</Button>
      </div>
    </div>
  );
}

// ─── Vendor Row ──────────────────────────────────────────────────────

interface VendorRowProps {
  vendor: QualifiedVendor;
  isSelected: boolean;
  isExpanded: boolean;
  selectedContactId: string | undefined;
  onToggle: () => void;
  onExpand: () => void;
  onChangeContact: (contactId: string) => void;
}

function VendorRow({
  vendor,
  isSelected,
  isExpanded,
  onToggle,
  onExpand,
}: VendorRowProps) {
  const contact = vendor.primary_contact;

  return (
    <>
      <tr
        className={cn(
          'cursor-pointer transition-colors hover:bg-secondary-50',
          isSelected && 'bg-primary-50/50',
        )}
        onClick={onExpand}
      >
        <td className="py-3 pr-2" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-secondary-300 accent-primary-600"
            checked={isSelected}
            onChange={onToggle}
            disabled={!contact}
          />
        </td>
        <td className="py-3 pr-4">
          <div className="font-medium text-secondary-900">{vendor.company_name}</div>
          {/* Mobile-only contact info */}
          <div className="mt-0.5 text-xs text-secondary-400 md:hidden">
            {contact?.full_name ?? 'No contact'}
          </div>
        </td>
        <td className="hidden py-3 pr-4 md:table-cell">
          {contact?.full_name ?? <span className="text-secondary-400">\u2014</span>}
        </td>
        <td className="hidden py-3 pr-4 text-secondary-600 lg:table-cell">
          {contact?.email ?? '\u2014'}
        </td>
        <td className="py-3 pr-4 text-right text-secondary-600">
          {vendor.distance_miles != null ? `${vendor.distance_miles.toFixed(1)} mi` : '\u2014'}
        </td>
        <td className="hidden py-3 pr-4 md:table-cell">
          {vendor.insurance_expiration_date ? (
            <span
              className={cn(
                'text-xs',
                vendor.insurance_days_remaining != null && vendor.insurance_days_remaining < 30
                  ? 'text-warning-600'
                  : 'text-secondary-600',
              )}
            >
              {formatDate(vendor.insurance_expiration_date)}
            </span>
          ) : (
            <span className="text-secondary-400">\u2014</span>
          )}
        </td>
        <td className="hidden py-3 pr-4 text-center lg:table-cell">
          <span className="text-secondary-600">
            {vendor.current_active_jobs}/{vendor.max_active_jobs ?? '\u221e'}
          </span>
        </td>
        <td className="py-3 text-center">
          {vendor.has_unresolved_flags ? (
            <span
              className="inline-flex cursor-help items-center gap-1 text-warning-600"
              title={vendor.flag_reasons.map((r) => r.replace(/_/g, ' ')).join(', ')}
            >
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              <span className="text-xs">{vendor.unresolved_flag_count}</span>
            </span>
          ) : (
            <span className="text-secondary-300">\u2014</span>
          )}
        </td>
      </tr>
      {/* Expanded row — contact details */}
      {isExpanded && (
        <tr>
          <td colSpan={8} className="bg-secondary-50 px-4 py-3">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-secondary-500">
                Contact Details
              </p>
              {contact ? (
                <div className="rounded-lg bg-white p-3 text-sm">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <div>
                      <span className="text-xs text-secondary-500">Name</span>
                      <p className="font-medium text-secondary-900">{contact.full_name}</p>
                    </div>
                    <div>
                      <span className="text-xs text-secondary-500">Email</span>
                      <p className="text-secondary-900">{contact.email}</p>
                    </div>
                    <div>
                      <span className="text-xs text-secondary-500">Phone</span>
                      <p className="text-secondary-900">{contact.phone ?? '\u2014'}</p>
                    </div>
                  </div>
                  {vendor.contact_warning && (
                    <p className="mt-2 text-xs text-warning-600">{vendor.contact_warning}</p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-secondary-500">
                  No contacts available for this vendor.
                </p>
              )}
              {vendor.has_unresolved_flags && (
                <div className="mt-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-secondary-500">
                    Flags
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {vendor.flag_reasons.map((reason, i) => (
                      <StatusBadge key={i} status={reason} variant="warning" size="sm" />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
