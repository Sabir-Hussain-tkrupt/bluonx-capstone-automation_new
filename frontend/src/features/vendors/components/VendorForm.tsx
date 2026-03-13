import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { TradeMultiSelect } from './TradeMultiSelect';
import type { Vendor } from '@/features/vendors/api/vendor.queries';
import { useState } from 'react';

const vendorSchema = z.object({
  company_name: z.string().min(2, 'Company name is required (min 2 characters)'),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().optional(),
  zip_code: z.string().optional(),
  insurance_expiration_date: z.string().optional(),
  insurance_coverage_amount: z.coerce.number().min(0, 'Must be >= 0').optional().or(z.literal('')),
  bonding_capacity: z.coerce.number().min(0, 'Must be >= 0').optional().or(z.literal('')),
  max_active_jobs: z.coerce.number().int().min(0, 'Must be >= 0').optional().or(z.literal('')),
  onboarding_status: z.enum(['pending', 'partial', 'complete']),
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
      insurance_expiration_date: vendor?.insurance_expiration_date ?? '',
      insurance_coverage_amount: vendor?.insurance_coverage_amount ?? ('' as unknown as number),
      bonding_capacity: vendor?.bonding_capacity ?? ('' as unknown as number),
      max_active_jobs: vendor?.max_active_jobs ?? ('' as unknown as number),
      onboarding_status: vendor?.onboarding_status ?? 'pending',
      status: vendor?.status ?? 'active',
      notes: vendor?.notes ?? '',
    },
  });

  const handleFormSubmit = (data: VendorFormValues) => {
    const cleanedData = {
      ...data,
      insurance_coverage_amount: data.insurance_coverage_amount === '' ? undefined : Number(data.insurance_coverage_amount),
      bonding_capacity: data.bonding_capacity === '' ? undefined : Number(data.bonding_capacity),
      max_active_jobs: data.max_active_jobs === '' ? undefined : Number(data.max_active_jobs),
      insurance_expiration_date: data.insurance_expiration_date || undefined,
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
    onClose();
  };

  const addContact = () => {
    if (!contactName.trim() || !contactEmail.trim()) return;
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
  };

  const removeContact = (idx: number) => {
    setContacts(contacts.filter((_, i) => i !== idx));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit Vendor' : 'Add Vendor'}
      size="lg"
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
      <form id="vendor-form" onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
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
            <FormField label="Onboarding Status">
              <Select
                {...register('onboarding_status')}
                options={[
                  { value: 'pending', label: 'Pending' },
                  { value: 'partial', label: 'Partial' },
                  { value: 'complete', label: 'Complete' },
                ]}
              />
            </FormField>
          </div>
        </div>

        {/* Insurance & Capacity */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Insurance & Capacity</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Insurance Expiration" error={errors.insurance_expiration_date?.message}>
              <TextInput type="date" {...register('insurance_expiration_date')} />
            </FormField>
            <FormField label="Insurance Coverage ($)" error={errors.insurance_coverage_amount?.message}>
              <TextInput
                type="number"
                step="0.01"
                min="0"
                {...register('insurance_coverage_amount')}
                error={errors.insurance_coverage_amount?.message}
              />
            </FormField>
            <FormField label="Bonding Capacity ($)" error={errors.bonding_capacity?.message}>
              <TextInput
                type="number"
                step="0.01"
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
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Contacts</h3>

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
                      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                      </svg>
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
