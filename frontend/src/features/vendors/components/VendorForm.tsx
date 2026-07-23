import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { TradeMultiSelect } from './TradeMultiSelect';
import { isValidEmail } from '@/utils/validation';
import type { Vendor } from '@/features/vendors/api/vendor.queries';
import { useState } from 'react';

const vendorSchema = z.object({
  // trim() runs before the length checks, so a whitespace-only name fails
  // min-length here instead of passing and being stored padded.
  company_name: z.string().trim().min(2, 'Company name is required (min 2 characters)').max(255, 'Company name must be 255 characters or fewer'),
  address: z.string().optional(),
  city: z.string().max(100, 'City must be 100 characters or fewer').optional().or(z.literal('')),
  state: z.string().max(50, 'State must be 50 characters or fewer').optional().or(z.literal('')),
  zip_code: z.string().max(20, 'ZIP code must be 20 characters or fewer').optional().or(z.literal('')),
  insurance_coverage_amount: z.coerce.number().min(0, 'Must be >= 0').optional().or(z.literal('')),
  bonding_capacity: z.coerce.number().min(0, 'Must be >= 0').optional().or(z.literal('')),
  max_active_jobs: z.coerce.number().int().min(0, 'Must be >= 0').optional().or(z.literal('')),
  onboarding_status: z.enum(['pending', 'partial', 'complete']),  // 'complete' is edit-only; see the Select below
  status: z.enum(['active', 'inactive', 'suspended']),
  notes: z.string().optional(),
});

type VendorFormValues = z.infer<typeof vendorSchema>;

interface VendorFormProps {
  isOpen: boolean;
  onClose: () => void;
  vendor?: Vendor;
  onSubmit: (data: VendorFormValues & { trade_ids?: string[]; contacts?: ContactInline[] }) => void;
  isLoading?: boolean;
}

interface ContactInline {
  full_name: string;
  email: string;
  phone?: string;
  title?: string;
  is_primary?: boolean;
}

export function VendorForm({ isOpen, onClose, vendor, onSubmit, isLoading = false }: VendorFormProps) {
  const isEdit = !!vendor;
  const [selectedTradeIds, setSelectedTradeIds] = useState<string[]>([]);
  const [contacts, setContacts] = useState<ContactInline[]>([]);
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactTitle, setContactTitle] = useState('');

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm({
    resolver: zodResolver(vendorSchema),
    defaultValues: {
      company_name: vendor?.company_name ?? '',
      address: vendor?.address ?? '',
      city: vendor?.city ?? '',
      state: vendor?.state ?? '',
      zip_code: vendor?.zip_code ?? '',
      insurance_coverage_amount: vendor?.insurance_coverage_amount ?? ('' as unknown as number),
      bonding_capacity: vendor?.bonding_capacity ?? ('' as unknown as number),
      max_active_jobs: vendor?.max_active_jobs ?? ('' as unknown as number),
      onboarding_status: vendor?.onboarding_status ?? 'pending',
      status: vendor?.status ?? 'active',
      notes: vendor?.notes ?? '',
    },
  });

  const [contactsError, setContactsError] = useState('');

  const handleFormSubmit = (data: VendorFormValues) => {
    // Require at least one contact when creating a new vendor
    if (!isEdit && contacts.length === 0) {
      setContactsError('At least one contact with email is required to create a vendor.');
      return;
    }
    setContactsError('');

    const cleanedData = {
      ...data,
      insurance_coverage_amount: data.insurance_coverage_amount === '' ? undefined : Number(data.insurance_coverage_amount),
      bonding_capacity: data.bonding_capacity === '' ? undefined : Number(data.bonding_capacity),
      max_active_jobs: data.max_active_jobs === '' ? undefined : Number(data.max_active_jobs),
      address: data.address || undefined,
      city: data.city || undefined,
      state: data.state || undefined,
      zip_code: data.zip_code || undefined,
      notes: data.notes || undefined,
    };

    if (!isEdit) {
      onSubmit({
        ...cleanedData,
        trade_ids: selectedTradeIds.length > 0 ? selectedTradeIds : undefined,
        contacts: contacts.length > 0 ? contacts : undefined,
      });
    } else {
      onSubmit(cleanedData);
    }
  };

  const handleClose = () => {
    reset();
    setSelectedTradeIds([]);
    setContacts([]);
    // The in-progress contact draft and its error are part of the form's
    // state too; leaving them behind resurfaces a stale row (and a stale red
    // banner) the next time the modal opens.
    setContactName('');
    setContactEmail('');
    setContactPhone('');
    setContactTitle('');
    setContactsError('');
    onClose();
  };

  const addContact = () => {
    if (!contactName.trim() || !contactEmail.trim()) return;
    // Catch a malformed address here rather than letting the API reject it,
    // where a 422 is flattened into a generic message that names no field.
    if (!isValidEmail(contactEmail)) {
      setContactsError('Enter a valid email address for the contact.');
      return;
    }
    setContacts([
      ...contacts,
      {
        full_name: contactName.trim(),
        email: contactEmail.trim(),
        phone: contactPhone.trim() || undefined,
        title: contactTitle.trim() || undefined,
        is_primary: contacts.length === 0,
      },
    ]);
    setContactName('');
    setContactEmail('');
    setContactPhone('');
    setContactTitle('');
    setContactsError('');
  };

  const removeContact = (idx: number) => {
    const wasPrimary = contacts[idx].is_primary;
    const updated = contacts.filter((_, i) => i !== idx);
    // If we removed the primary contact, promote the first remaining contact
    if (wasPrimary && updated.length > 0) {
      updated[0] = { ...updated[0], is_primary: true };
    }
    setContacts(updated);
    // Clear contacts error if still at least one contact
    if (updated.length > 0) setContactsError('');
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit Vendor' : 'Add Vendor'}
      size="lg"
      // A stray click on the backdrop should not discard a part-filled vendor.
      closeOnOverlayClick={false}
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="vendor-form"
            isLoading={isLoading}
          >
            {isEdit ? 'Save Changes' : 'Create Vendor'}
          </Button>
        </>
      }
    >
      <form
        id="vendor-form"
        onSubmit={handleSubmit(handleFormSubmit)}
        className="space-y-6"
        noValidate
      >
        {/* Company Info */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Company Information</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <FormField label="Company Name" required error={errors.company_name?.message}>
                <TextInput {...register('company_name')} error={errors.company_name?.message} />
              </FormField>
            </div>
            <div className="sm:col-span-2">
              <FormField label="Address" error={errors.address?.message}>
                <TextInput {...register('address')} />
              </FormField>
            </div>
            <FormField label="City" error={errors.city?.message}>
              <TextInput {...register('city')} />
            </FormField>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="State" error={errors.state?.message}>
                <TextInput {...register('state')} placeholder="MO" />
              </FormField>
              <FormField label="ZIP" error={errors.zip_code?.message}>
                <TextInput {...register('zip_code')} placeholder="63101" />
              </FormField>
            </div>
          </div>
        </div>

        {/* Status & Onboarding */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Status</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Status">
              <Select
                {...register('status')}
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive' },
                  { value: 'suspended', label: 'Suspended' },
                ]}
              />
            </FormField>
            <FormField
              label="Onboarding Status"
              hint={
                isEdit
                  ? undefined
                  : 'Mark complete after uploading an insurance certificate.'
              }
            >
              <Select
                {...register('onboarding_status')}
                options={
                  isEdit
                    ? [
                        { value: 'pending', label: 'Pending' },
                        { value: 'partial', label: 'Partial' },
                        { value: 'complete', label: 'Complete' },
                      ]
                    : [
                        { value: 'pending', label: 'Pending' },
                        { value: 'partial', label: 'Partial' },
                      ]
                }
              />
            </FormField>
          </div>
        </div>

        {/* Insurance & Capacity */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Insurance & Capacity</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Insurance Expiration is intentionally absent. The column is a
                derived mirror of MAX(expiration_date) over this vendor's valid
                insurance certificates, recomputed on every document upload and
                delete. A hand-typed value here would claim coverage no
                certificate backs (turning the pre-award "uninsurable" block
                into a pass) and would be silently overwritten by the next
                document change. Set it by uploading a certificate on the
                vendor detail page. */}
            <FormField label="Insurance Coverage ($)" error={errors.insurance_coverage_amount?.message}>
              <TextInput
                type="number"
                step="1000"
                min="0"
                {...register('insurance_coverage_amount')}
                error={errors.insurance_coverage_amount?.message}
              />
            </FormField>
            <FormField label="Bonding Capacity ($)" error={errors.bonding_capacity?.message}>
              <TextInput
                type="number"
                step="1000"
                min="0"
                {...register('bonding_capacity')}
                error={errors.bonding_capacity?.message}
              />
            </FormField>
            <FormField label="Max Active Jobs" error={errors.max_active_jobs?.message}>
              <TextInput
                type="number"
                min="0"
                {...register('max_active_jobs')}
                error={errors.max_active_jobs?.message}
              />
            </FormField>
          </div>
        </div>

        {/* Notes */}
        <FormField label="Notes" error={errors.notes?.message}>
          <textarea
            {...register('notes')}
            rows={3}
            className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
          />
        </FormField>

        {/* Trades (Create mode only) */}
        {!isEdit && (
          <div>
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Trade Associations</h3>
            <TradeMultiSelect
              selectedTradeIds={selectedTradeIds}
              onChange={setSelectedTradeIds}
            />
          </div>
        )}

        {/* Contacts (Create mode only) */}
        {!isEdit && (
          <div>
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">
              Contacts <span className="text-danger-500">*</span>
            </h3>
            {contactsError && (
              <p className="mb-3 rounded-lg border border-danger-200 bg-danger-50 px-3 py-2 text-sm text-danger-700">
                {contactsError}
              </p>
            )}

            {contacts.length > 0 && (
              <div className="mb-3 space-y-2">
                {contacts.map((c, idx) => (
                  <div
                    key={idx}
                    className="flex items-start justify-between gap-2 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2"
                  >
                    <div className="min-w-0 flex-1 text-sm">
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="font-medium">{c.full_name}</span>
                        {c.is_primary && (
                          <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs text-primary-700">
                            Primary
                          </span>
                        )}
                      </div>
                      <span className="block truncate text-secondary-500">{c.email}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeContact(idx)}
                      className="mt-1 shrink-0 text-secondary-400 hover:text-danger-600"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-lg border border-dashed border-secondary-300 p-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <TextInput
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  placeholder="Contact name *"
                  size="sm"
                />
                <TextInput
                  type="email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  placeholder="Email *"
                  size="sm"
                />
                <TextInput
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  placeholder="Phone"
                  size="sm"
                />
                <TextInput
                  value={contactTitle}
                  onChange={(e) => setContactTitle(e.target.value)}
                  placeholder="Title"
                  size="sm"
                />
              </div>
              <div className="mt-2 flex justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addContact}
                  disabled={!contactName.trim() || !contactEmail.trim()}
                >
                  + Add Contact
                </Button>
              </div>
            </div>
          </div>
        )}
      </form>
    </Modal>
  );
}
