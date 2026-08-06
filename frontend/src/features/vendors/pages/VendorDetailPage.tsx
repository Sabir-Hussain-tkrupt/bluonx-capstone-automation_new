import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { MoreHorizontal, Pencil, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { Card } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { useTabParam } from '@/hooks/useTabParam';
import { useVendor } from '@/features/vendors/hooks/useVendor';
import { useUpdateVendor } from '@/features/vendors/hooks/useUpdateVendor';
import { useDeleteVendor } from '@/features/vendors/hooks/useDeleteVendor';
import { useCreateContact, useUpdateContact, useDeleteContact } from '@/features/vendors/hooks/useVendorContacts';
import { useAddVendorTrades, useRemoveVendorTrade } from '@/features/vendors/hooks/useVendorTrades';
import { useDeleteVendorDocument, useVendorDocumentDownload } from '@/features/vendors/hooks/useVendorDocuments';
import {
  EMAIL_LOG_PAGE_SIZE,
  useVendorEmailLog,
} from '@/features/vendors/hooks/useVendorEmailLog';
import { EmailLogTable } from '@/features/bids/components/EmailLogTable';
import { VendorForm } from '@/features/vendors/components/VendorForm';
import { ContactForm } from '@/features/vendors/components/ContactForm';
import { TradeMultiSelect } from '@/features/vendors/components/TradeMultiSelect';
import { VendorDocumentUpload } from '@/features/vendors/components/VendorDocumentUpload';
import { DocumentList } from '@/components/ui/DocumentList';
import { Field } from '@/components/ui/Field';
import { AddressNotLocatableBadge } from '@/components/shared/AddressNotLocatableBadge';
import type { VendorContact } from '@/features/vendors/api/vendor.queries';
import type { StatusVariant } from '@/components/ui/types';
import { errorMessage } from '@/lib/api';
import { notifyGeocodeWarning } from '@/utils/geocodeToast';

/**
 * The destructive action awaiting confirmation.
 *
 * One dialog serves all four so they cannot drift: deleting a vendor used to
 * be the only one that asked, while removing a contact or a document — both
 * hard deletes — happened on a single click.
 */
type PendingAction =
  | { kind: 'deleteVendor' }
  | { kind: 'deleteContact'; contact: VendorContact }
  | { kind: 'removeTrade'; tradeId: string; label: string }
  | { kind: 'deleteDocument'; docId: string; label: string }
  | null;

// Module level, and the single source for both the tab ids the URL accepts and
// the rendered tab bar: a separate id list would drift from the labels.
const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'contacts', label: 'Contacts' },
  { id: 'trades', label: 'Trades' },
  { id: 'documents', label: 'Documents' },
  { id: 'flags', label: 'Flags' },
  { id: 'communication', label: 'Communication' },
];
const TAB_IDS = TABS.map((t) => t.id);

const statusVariantMap: Record<string, StatusVariant> = {
  active: 'success', inactive: 'neutral', suspended: 'danger',
};
const onboardingVariantMap: Record<string, StatusVariant> = {
  pending: 'warning', partial: 'info', complete: 'success',
};
const flagReasonLabels: Record<string, string> = {
  missed_deadline: 'Missed Deadline', poor_quality: 'Poor Quality', unresponsive: 'Unresponsive', other: 'Other',
};

export function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: vendor, isLoading, error, refetch, isFetching } = useVendor(id!);
  const updateVendorMutation = useUpdateVendor();
  const deleteVendorMutation = useDeleteVendor();
  const createContactMutation = useCreateContact();
  const updateContactMutation = useUpdateContact();
  const deleteContactMutation = useDeleteContact();
  const addTradesMutation = useAddVendorTrades();
  const removeTradesMutation = useRemoveVendorTrade();
  const deleteDocMutation = useDeleteVendorDocument();
  const { download: downloadDoc, downloadingId } = useVendorDocumentDownload();

  const [activeTab, setActiveTab] = useTabParam(TAB_IDS);
  const [emailLogPage, setEmailLogPage] = useState(1);
  const { data: emailLog, isLoading: emailLogLoading } = useVendorEmailLog(
    id!,
    activeTab === 'communication',
    emailLogPage,
  );
  const [showEditForm, setShowEditForm] = useState(false);
  const [confirming, setConfirming] = useState<PendingAction>(null);
  const [showAddContact, setShowAddContact] = useState(false);
  const [editingContact, setEditingContact] = useState<VendorContact | null>(null);
  const [showAddTrades, setShowAddTrades] = useState(false);
  const [newTradeIds, setNewTradeIds] = useState<string[]>([]);
  const [showUploadDoc, setShowUploadDoc] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="70%" />
        <Skeleton height="400px" />
      </div>
    );
  }

  // A missing vendor and an unreachable server are different problems and need
  // different messages: telling someone their vendor was deleted when the
  // network dropped sends them looking for the wrong thing.
  if (error || !vendor) {
    const status = error?.status;
    if (!error || status === 404) {
      return (
        <Alert variant="danger" title="Vendor not found">
          The vendor you are looking for does not exist or has been deleted.
        </Alert>
      );
    }
    return (
      <Alert variant="danger" title="Could not load vendor">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => refetch()} isLoading={isFetching}>
            Retry
          </Button>
        </div>
      </Alert>
    );
  }

  const contacts = vendor.vendor_contacts ?? [];
  const trades = vendor.vendor_trades ?? [];
  const documents = vendor.vendor_documents ?? [];
  const flags = vendor.vendor_flags ?? [];

  const closeConfirm = () => setConfirming(null);

  const handleConfirm = () => {
    if (!confirming) return;

    const done = (message: string) => () => {
      closeConfirm();
      toast({ variant: 'success', message });
    };
    const failed = (fallback: string) => (err: unknown) => {
      closeConfirm();
      toast({ variant: 'danger', message: errorMessage(err, fallback) });
    };

    switch (confirming.kind) {
      case 'deleteVendor':
        deleteVendorMutation.mutate(id!, {
          onSuccess: () => {
            closeConfirm();
            toast({ variant: 'success', message: 'Vendor deleted.' });
            navigate('/vendors');
          },
          onError: failed('Failed to delete vendor.'),
        });
        break;
      case 'deleteContact':
        deleteContactMutation.mutate(
          { vendorId: id!, contactId: confirming.contact.id },
          { onSuccess: done('Contact deleted.'), onError: failed('Failed to delete contact.') },
        );
        break;
      case 'removeTrade':
        removeTradesMutation.mutate(
          { vendorId: id!, tradeId: confirming.tradeId },
          { onSuccess: done('Trade removed.'), onError: failed('Failed to remove trade.') },
        );
        break;
      case 'deleteDocument':
        deleteDocMutation.mutate(
          { vendorId: id!, docId: confirming.docId },
          { onSuccess: done('Document deleted.'), onError: failed('Failed to delete document.') },
        );
        break;
    }
  };

  const confirmIsPending =
    deleteVendorMutation.isPending ||
    deleteContactMutation.isPending ||
    removeTradesMutation.isPending ||
    deleteDocMutation.isPending;

  // Say what is being removed and whether it can be undone. Contacts,
  // documents and trade links are hard deletes; the vendor itself is not.
  const confirmCopy = (() => {
    switch (confirming?.kind) {
      case 'deleteContact':
        return {
          title: 'Delete Contact',
          confirmText: 'Delete Contact',
          message: (
            <>
              Delete <strong>{confirming.contact.full_name}</strong>? This cannot be undone.
              {confirming.contact.is_primary && contacts.length > 1 && (
                <> The next contact will become the primary contact.</>
              )}
            </>
          ),
        };
      case 'removeTrade':
        return {
          title: 'Remove Trade',
          confirmText: 'Remove Trade',
          message: (
            <>
              Remove <strong>{confirming.label}</strong> from this vendor? They will stop
              matching bid packages for this trade. You can add it back later.
            </>
          ),
        };
      case 'deleteDocument':
        return {
          title: 'Delete Document',
          confirmText: 'Delete Document',
          message: (
            <>
              Delete <strong>{confirming.label}</strong>? The file is removed from storage
              and cannot be recovered.
            </>
          ),
        };
      default:
        return {
          title: 'Delete Vendor',
          confirmText: 'Delete Vendor',
          message: (
            <>
              Are you sure you want to delete <strong>{vendor.company_name}</strong>? This
              soft-deletes the vendor and they will no longer appear in lists. Deletion is
              blocked while they have live bids or active contracts.
            </>
          ),
        };
    }
  })();

  const handleSaveTrades = () => {
    if (newTradeIds.length === 0) return;
    addTradesMutation.mutate(
      { vendorId: id!, trade_ids: newTradeIds },
      {
        onSuccess: () => {
          setShowAddTrades(false);
          setNewTradeIds([]);
          toast({ variant: 'success', message: 'Trades updated.' });
        },
        onError: (err) => toast({
          variant: 'danger',
          message: errorMessage(err, 'Failed to add trades.'),
        }),
      },
    );
  };

  const existingTradeIds = trades.map((t) => t.trade_id);
  const isOnlyContact = contacts.length === 1;

  // Derived from the pending action so the row spinner tracks the actual
  // in-flight delete rather than a separate piece of state to keep in sync.
  const deletingDocId =
    confirming?.kind === 'deleteDocument' && deleteDocMutation.isPending
      ? confirming.docId
      : null;

  const tabCounts: Record<string, number | undefined> = {
    contacts: contacts.length,
    trades: trades.length,
    documents: documents.length,
    flags: flags.length,
    // The email log is only fetched once its tab is opened, so before that a
    // count would always read 0 and look like "no messages" rather than
    // "not loaded yet". Show it only when we actually know. The badge is the
    // server-side total, not the page length, which would just read 25.
    communication: emailLog?.total,
  };
  const tabDefs = TABS.map((t) => ({ ...t, count: tabCounts[t.id] }));

  const unresolvedFlagCount = flags.filter((f) => !f.is_resolved).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">{vendor.company_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge status={vendor.status} variant={statusVariantMap[vendor.status] ?? 'neutral'} />
            <StatusBadge
              status={vendor.onboarding_status}
              variant={onboardingVariantMap[vendor.onboarding_status] ?? 'neutral'}
            />
            {unresolvedFlagCount > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-danger-100 px-2.5 py-0.5 text-xs font-medium text-danger-700">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger-500" />
                {unresolvedFlagCount} Active Flag(s)
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="primary"
            leftIcon={<Pencil className="h-4 w-4" />}
            onClick={() => setShowEditForm(true)}
          >
            Edit
          </Button>
          <DropdownMenu
            trigger={
              <IconButton
                variant="outline"
                size="md"
                icon={<MoreHorizontal className="h-4 w-4" />}
                aria-label="More actions"
              />
            }
          >
            <DropdownMenuItem
              icon={<Trash2 className="h-4 w-4" />}
              destructive
              onClick={() => setConfirming({ kind: 'deleteVendor' })}
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenu>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabDefs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' && (
          <Card>
            <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-2">
              <div>
                <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Location</h3>
                <dl className="divide-y divide-secondary-100">
                  <Field
                    label="Address"
                    value={
                      <span className="inline-flex flex-wrap items-center justify-end gap-2">
                        {vendor.address}
                        <AddressNotLocatableBadge
                          address={vendor.address}
                          latitude={vendor.latitude}
                          entity="vendor"
                        />
                      </span>
                    }
                  />
                  <Field label="City" value={vendor.city} />
                  <Field label="State" value={vendor.state} />
                  <Field label="ZIP Code" value={vendor.zip_code} />
                </dl>
              </div>
              <div>
                <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Insurance & Capacity</h3>
                <dl className="divide-y divide-secondary-100">
                  <Field label="Insurance Expiration" value={vendor.insurance_expiration_date} />
                  {/* Compare against null, not truthiness: a genuine 0 is a
                      real value and must not render as "not set". */}
                  <Field
                    label="Insurance Coverage"
                    value={vendor.insurance_coverage_amount != null ? `$${Number(vendor.insurance_coverage_amount).toLocaleString()}` : null}
                  />
                  <Field
                    label="Bonding Capacity"
                    value={vendor.bonding_capacity != null ? `$${Number(vendor.bonding_capacity).toLocaleString()}` : null}
                  />
                  <Field
                    label="Active Jobs"
                    value={
                      vendor.max_active_jobs != null
                        ? `${vendor.current_active_jobs} / ${vendor.max_active_jobs}`
                        : `${vendor.current_active_jobs}`
                    }
                  />
                </dl>
              </div>
              {vendor.notes && (
                <div className="md:col-span-2">
                  <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Notes</h3>
                  <p className="text-sm text-secondary-700 whitespace-pre-wrap">{vendor.notes}</p>
                </div>
              )}
            </div>
          </Card>
        )}

        {activeTab === 'contacts' && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setShowAddContact(true)}>+ Add Contact</Button>
            </div>
            {contacts.length === 0 ? (
              <EmptyState title="No contacts" description="Add a contact for this vendor." />
            ) : (
              <div className="space-y-3">
                {contacts.map((c) => (
                  <Card key={c.id}>
                    <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-secondary-900">{c.full_name}</span>
                          {c.is_primary && <StatusBadge status="primary" variant="info" />}
                        </div>
                        <p className="mt-1 truncate text-sm text-secondary-500">{c.email}</p>
                        {c.phone && <p className="text-sm text-secondary-500">{c.phone}</p>}
                        {c.title && <p className="text-sm text-secondary-400">{c.title}</p>}
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <Button size="sm" variant="ghost" onClick={() => setEditingContact(c)}>Edit</Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          // A vendor must keep at least one contact: the
                          // invitation and milestone emails resolve their
                          // recipient through it. The API enforces this with a
                          // 409; disabling here avoids offering an action that
                          // cannot succeed.
                          disabled={isOnlyContact}
                          title={
                            isOnlyContact
                              ? 'A vendor must have at least one contact. Add another before removing this one.'
                              : undefined
                          }
                          onClick={() => setConfirming({ kind: 'deleteContact', contact: c })}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
            <Modal isOpen={showAddContact} onClose={() => setShowAddContact(false)} title="Add Contact" size="md">
              <ContactForm
                onCancel={() => setShowAddContact(false)}
                isLoading={createContactMutation.isPending}
                hasPrimaryContact={contacts.some((c) => c.is_primary)}
                contactCount={contacts.length}
                onSubmit={(data) => {
                  createContactMutation.mutate(
                    { vendorId: id!, ...data },
                    {
                      onSuccess: () => { setShowAddContact(false); toast({ variant: 'success', message: 'Contact added.' }); },
                      onError: (err) => toast({
                        variant: 'danger',
                        message: errorMessage(err, 'Failed to add contact.'),
                      }),
                    },
                  );
                }}
              />
            </Modal>
            <Modal isOpen={!!editingContact} onClose={() => setEditingContact(null)} title="Edit Contact" size="md">
              {editingContact && (
                <ContactForm
                  contact={editingContact}
                  onCancel={() => setEditingContact(null)}
                  isLoading={updateContactMutation.isPending}
                  hasPrimaryContact={contacts.some((c) => c.is_primary)}
                  contactCount={contacts.length}
                  onSubmit={(data) => {
                    updateContactMutation.mutate(
                      { vendorId: id!, contactId: editingContact.id, ...data },
                      {
                        onSuccess: () => { setEditingContact(null); toast({ variant: 'success', message: 'Contact updated.' }); },
                        onError: (err) => toast({
                          variant: 'danger',
                          message: errorMessage(err, 'Failed to update contact.'),
                        }),
                      },
                    );
                  }}
                />
              )}
            </Modal>
          </div>
        )}

        {activeTab === 'trades' && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setShowAddTrades(true)}>+ Add Trades</Button>
            </div>
            {trades.length === 0 ? (
              <EmptyState title="No trades" description="Associate trades with this vendor." />
            ) : (
              <div className="flex flex-wrap gap-2">
                {trades.map((vt) => (
                  <div key={vt.id} className="inline-flex items-center gap-2 rounded-lg border border-secondary-200 bg-white px-3 py-2">
                    <div>
                      <span className="text-sm font-medium text-secondary-900">{vt.trades?.name ?? 'Unknown'}</span>
                      <span className="ml-2 text-xs text-secondary-400">
                        {vt.trades?.phase === 'due_diligence' ? 'DD' : vt.trades?.phase === 'development' ? 'Dev' : 'Both'}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setConfirming({
                          kind: 'removeTrade',
                          tradeId: vt.trade_id,
                          label: vt.trades?.name ?? 'this trade',
                        })
                      }
                      aria-label={`Remove ${vt.trades?.name ?? 'trade'}`}
                      className="text-secondary-400 hover:text-danger-600"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <Modal
              isOpen={showAddTrades}
              onClose={() => { setShowAddTrades(false); setNewTradeIds([]); }}
              title="Add Trades"
              size="lg"
              bodyClassName="overflow-y-visible"
              footer={
                <>
                  <Button variant="ghost" onClick={() => { setShowAddTrades(false); setNewTradeIds([]); }}>Cancel</Button>
                  <Button onClick={handleSaveTrades} isLoading={addTradesMutation.isPending} disabled={newTradeIds.length === 0}>
                    Add Selected Trades
                  </Button>
                </>
              }
            >
              {/* Trades the vendor already has are shown selected but locked,
                  rather than silently discarding clicks on them. Removal
                  happens from the Trades tab, where it is confirmed. */}
              <TradeMultiSelect
                selectedTradeIds={[...existingTradeIds, ...newTradeIds]}
                lockedTradeIds={existingTradeIds}
                lockedHint="Already associated. Remove it from the Trades tab."
                onChange={(ids) => setNewTradeIds(ids.filter((tid) => !existingTradeIds.includes(tid)))}
              />
            </Modal>
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setShowUploadDoc(true)}>+ Upload Document</Button>
            </div>
            <DocumentList
              documents={documents}
              onDownload={(docId) => downloadDoc(id!, docId)}
              onDelete={(docId) =>
                setConfirming({
                  kind: 'deleteDocument',
                  docId,
                  label: documents.find((d) => d.id === docId)?.file_name ?? 'this document',
                })
              }
              isDeleting={deletingDocId}
              isDownloading={downloadingId}
              emptyMessage="No documents uploaded yet. Upload W-9, Insurance Certificate, or Master Trade Agreement."
            />
            <VendorDocumentUpload
              vendorId={id!}
              isOpen={showUploadDoc}
              onClose={() => setShowUploadDoc(false)}
              existingDocuments={vendor.vendor_documents}
            />
          </div>
        )}

        {activeTab === 'flags' && (
          <div>
            {flags.length === 0 ? (
              <EmptyState title="No flags" description="This vendor has no performance flags." />
            ) : (
              <div className="space-y-3">
                {flags.map((flag) => (
                  <Card key={flag.id}>
                    <div className="p-4">
                      <div className="flex items-center justify-between">
                        <StatusBadge status={flag.is_resolved ? 'resolved' : 'active'} variant={flag.is_resolved ? 'success' : 'danger'} />
                        <span className="text-xs text-secondary-400">{new Date(flag.created_at).toLocaleDateString()}</span>
                      </div>
                      <p className="mt-2 text-sm font-medium text-secondary-900">{flagReasonLabels[flag.reason] ?? flag.reason}</p>
                      {flag.notes && <p className="mt-1 text-sm text-secondary-600">{flag.notes}</p>}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'communication' && (
          <EmailLogTable
            items={emailLog?.items ?? []}
            isLoading={emailLogLoading}
            pagination={{
              page: emailLogPage,
              pageSize: EMAIL_LOG_PAGE_SIZE,
              total: emailLog?.total ?? 0,
              onPageChange: setEmailLogPage,
            }}
          />
        )}
      </Tabs>

      {/* Edit Vendor Modal.
          Mounted only while open: React Hook Form captures defaultValues at
          mount, so a form left mounted keeps serving the values the vendor had
          when the page first loaded, even after a save. */}
      {showEditForm && (
        <VendorForm
          isOpen={showEditForm}
          onClose={() => setShowEditForm(false)}
          vendor={vendor}
          isLoading={updateVendorMutation.isPending}
          onSubmit={(formData) => {
            updateVendorMutation.mutate(
              { id: id!, ...formData } as Parameters<typeof updateVendorMutation.mutate>[0],
              {
                onSuccess: (updated) => {
                  setShowEditForm(false);
                  toast({ variant: 'success', message: 'Vendor updated.' });
                  notifyGeocodeWarning(toast, updated);
                },
                onError: (err) => toast({
                  variant: 'danger',
                  message: errorMessage(err, 'Failed to update vendor.'),
                }),
              },
            );
          }}
        />
      )}

      {/* One confirmation for every destructive action on this page. */}
      <ConfirmDialog
        isOpen={confirming !== null}
        title={confirmCopy.title}
        message={confirmCopy.message}
        confirmText={confirmCopy.confirmText}
        isLoading={confirmIsPending}
        onConfirm={handleConfirm}
        onCancel={closeConfirm}
      />
    </div>
  );
}
