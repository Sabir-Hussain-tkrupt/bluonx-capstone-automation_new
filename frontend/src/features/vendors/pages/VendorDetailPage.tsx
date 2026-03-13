import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { useVendor } from '@/features/vendors/hooks/useVendor';
import { useUpdateVendor } from '@/features/vendors/hooks/useUpdateVendor';
import { useDeleteVendor } from '@/features/vendors/hooks/useDeleteVendor';
import { useCreateContact, useUpdateContact, useDeleteContact } from '@/features/vendors/hooks/useVendorContacts';
import { useAddVendorTrades, useRemoveVendorTrade } from '@/features/vendors/hooks/useVendorTrades';
import { VendorForm } from '@/features/vendors/components/VendorForm';
import { ContactForm } from '@/features/vendors/components/ContactForm';
import { TradeMultiSelect } from '@/features/vendors/components/TradeMultiSelect';
import type { VendorContact } from '@/features/vendors/api/vendor.queries';
import type { StatusVariant } from '@/components/ui/types';

const statusVariantMap: Record<string, StatusVariant> = {
  active: 'success', inactive: 'neutral', suspended: 'danger',
};
const onboardingVariantMap: Record<string, StatusVariant> = {
  pending: 'warning', partial: 'info', complete: 'success',
};
const docTypeLabels: Record<string, string> = {
  w9: 'W-9', insurance_certificate: 'Insurance Certificate', master_trade_agreement: 'Master Trade Agreement',
};
const flagReasonLabels: Record<string, string> = {
  missed_deadline: 'Missed Deadline', poor_quality: 'Poor Quality', unresponsive: 'Unresponsive', other: 'Other',
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-secondary-500">{label}</dt>
      <dd className="text-right text-secondary-900">{value || '\u2014'}</dd>
    </div>
  );
}

export function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: vendor, isLoading, error } = useVendor(id!);
  const updateVendorMutation = useUpdateVendor();
  const deleteVendorMutation = useDeleteVendor();
  const createContactMutation = useCreateContact();
  const updateContactMutation = useUpdateContact();
  const deleteContactMutation = useDeleteContact();
  const addTradesMutation = useAddVendorTrades();
  const removeTradesMutation = useRemoveVendorTrade();

  const [activeTab, setActiveTab] = useState('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showAddContact, setShowAddContact] = useState(false);
  const [editingContact, setEditingContact] = useState<VendorContact | null>(null);
  const [showAddTrades, setShowAddTrades] = useState(false);
  const [newTradeIds, setNewTradeIds] = useState<string[]>([]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="70%" />
        <Skeleton height="400px" />
      </div>
    );
  }

  if (error || !vendor) {
    return (
      <Alert variant="danger" title="Vendor not found">
        The vendor you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  const contacts = vendor.vendor_contacts ?? [];
  const trades = vendor.vendor_trades ?? [];
  const documents = vendor.vendor_documents ?? [];
  const flags = vendor.vendor_flags ?? [];

  const handleDelete = () => {
    deleteVendorMutation.mutate(id!, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Vendor deleted.' });
        navigate('/vendors');
      },
      onError: () => toast({ variant: 'danger', message: 'Failed to delete vendor.' }),
    });
  };

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
        onError: () => toast({ variant: 'danger', message: 'Failed to add trades.' }),
      },
    );
  };

  const existingTradeIds = trades.map((t) => t.trade_id);

  const tabDefs = [
    { id: 'overview', label: 'Overview' },
    { id: 'contacts', label: `Contacts (${contacts.length})` },
    { id: 'trades', label: `Trades (${trades.length})` },
    { id: 'documents', label: `Documents (${documents.length})` },
    { id: 'flags', label: `Flags (${flags.length})` },
  ];

  const unresolvedFlagCount = flags.filter((f) => !f.is_resolved).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/vendors')}
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
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={() => setShowEditForm(true)}>Edit</Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>Delete</Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabDefs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' && (
          <Card>
            <div className="grid grid-cols-1 gap-6 p-6 md:grid-cols-2">
              <div>
                <h3 className="mb-3 text-sm font-semibold text-secondary-900">Location</h3>
                <dl className="divide-y divide-secondary-100">
                  <InfoRow label="Address" value={vendor.address} />
                  <InfoRow label="City" value={vendor.city} />
                  <InfoRow label="State" value={vendor.state} />
                  <InfoRow label="ZIP Code" value={vendor.zip_code} />
                </dl>
              </div>
              <div>
                <h3 className="mb-3 text-sm font-semibold text-secondary-900">Insurance & Capacity</h3>
                <dl className="divide-y divide-secondary-100">
                  <InfoRow label="Insurance Expiration" value={vendor.insurance_expiration_date} />
                  <InfoRow
                    label="Insurance Coverage"
                    value={vendor.insurance_coverage_amount ? `$${Number(vendor.insurance_coverage_amount).toLocaleString()}` : null}
                  />
                  <InfoRow
                    label="Bonding Capacity"
                    value={vendor.bonding_capacity ? `$${Number(vendor.bonding_capacity).toLocaleString()}` : null}
                  />
                  <InfoRow
                    label="Active Jobs"
                    value={
                      vendor.max_active_jobs
                        ? `${vendor.current_active_jobs} / ${vendor.max_active_jobs}`
                        : `${vendor.current_active_jobs}`
                    }
                  />
                </dl>
              </div>
              {vendor.notes && (
                <div className="md:col-span-2">
                  <h3 className="mb-2 text-sm font-semibold text-secondary-900">Notes</h3>
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
                          onClick={() => {
                            deleteContactMutation.mutate(
                              { vendorId: id!, contactId: c.id },
                              {
                                onSuccess: () => toast({ variant: 'success', message: 'Contact deleted.' }),
                                onError: () => toast({ variant: 'danger', message: 'Failed to delete contact.' }),
                              },
                            );
                          }}
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
                onSubmit={(data) => {
                  createContactMutation.mutate(
                    { vendorId: id!, ...data },
                    {
                      onSuccess: () => { setShowAddContact(false); toast({ variant: 'success', message: 'Contact added.' }); },
                      onError: () => toast({ variant: 'danger', message: 'Failed to add contact.' }),
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
                  onSubmit={(data) => {
                    updateContactMutation.mutate(
                      { vendorId: id!, contactId: editingContact.id, ...data },
                      {
                        onSuccess: () => { setEditingContact(null); toast({ variant: 'success', message: 'Contact updated.' }); },
                        onError: () => toast({ variant: 'danger', message: 'Failed to update contact.' }),
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
                      onClick={() => {
                        removeTradesMutation.mutate(
                          { vendorId: id!, tradeId: vt.trade_id },
                          {
                            onSuccess: () => toast({ variant: 'success', message: 'Trade removed.' }),
                            onError: () => toast({ variant: 'danger', message: 'Failed to remove trade.' }),
                          },
                        );
                      }}
                      className="text-secondary-400 hover:text-danger-600"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                      </svg>
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
              <TradeMultiSelect
                selectedTradeIds={[...existingTradeIds, ...newTradeIds]}
                onChange={(ids) => setNewTradeIds(ids.filter((tid) => !existingTradeIds.includes(tid)))}
              />
            </Modal>
          </div>
        )}

        {activeTab === 'documents' && (
          <div>
            {documents.length === 0 ? (
              <EmptyState title="No documents" description="Documents will be uploaded in the document management module (Task 3.4)." />
            ) : (
              <div className="space-y-3">
                {documents.map((doc) => (
                  <Card key={doc.id}>
                    <div className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0 flex-1">
                        <span className="font-medium text-secondary-900">{doc.file_name}</span>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-secondary-500">
                          <span>{docTypeLabels[doc.document_type] ?? doc.document_type}</span>
                          {doc.expiration_date && <span>Expires: {doc.expiration_date}</span>}
                        </div>
                      </div>
                      <div className="shrink-0">
                        <StatusBadge status={doc.status} />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
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
      </Tabs>

      {/* Edit Vendor Modal */}
      <VendorForm
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        vendor={vendor}
        isLoading={updateVendorMutation.isPending}
        onSubmit={(formData) => {
          updateVendorMutation.mutate(
            { id: id!, ...formData } as Parameters<typeof updateVendorMutation.mutate>[0],
            {
              onSuccess: () => { setShowEditForm(false); toast({ variant: 'success', message: 'Vendor updated.' }); },
              onError: () => toast({ variant: 'danger', message: 'Failed to update vendor.' }),
            },
          );
        }}
      />

      {/* Delete Confirmation */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        title="Delete Vendor"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} isLoading={deleteVendorMutation.isPending}>Delete Vendor</Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete <strong>{vendor.company_name}</strong>?
          This action will soft-delete the vendor and they will no longer appear in lists.
        </p>
      </Modal>
    </div>
  );
}
