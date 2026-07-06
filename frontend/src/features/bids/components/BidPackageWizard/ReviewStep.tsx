import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Modal } from '@/components/ui/Modal';
import { Table } from '@/components/ui/Table';
import { useBidTemplates } from '@/features/bid-templates/hooks/useBidTemplates';
import type { Column } from '@/components/ui/Table';
import type { Task } from '@/features/tasks/api/task.queries';
import type { WizardData, VendorSelection } from '@/features/bids/types';
import { useQualifiedVendors } from '@/features/bids/hooks/useQualifiedVendors';

interface ReviewStepProps {
  data: WizardData;
  task: Task;
  onSubmit: () => void;
  onBack: () => void;
  isSubmitting: boolean;
}

interface VendorRow {
  vendor_id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
}

function formatDeadline(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const vendorColumns: Column<VendorRow>[] = [
  { id: 'company_name', header: 'Company', accessor: 'company_name' },
  { id: 'contact_name', header: 'Contact', accessor: 'contact_name' },
  { id: 'contact_email', header: 'Email', accessor: 'contact_email' },
];

export function ReviewStep({ data, task, onSubmit, onBack, isSubmitting }: ReviewStepProps) {
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: templatesData } = useBidTemplates({ page_size: 100 });
  const { data: vendorData } = useQualifiedVendors(task.id);

  const templateName =
    templatesData?.items.find((t) => t.id === data.bidTemplateId)?.name ?? 'Unknown Template';

  // Build vendor display rows from selections + vendor data
  const allVendors = [
    ...(vendorData?.qualified_vendors ?? []),
    ...(vendorData?.disqualified_vendors ?? []),
  ];

  const vendorRows: VendorRow[] = data.vendorSelections.map((sel: VendorSelection) => {
    const vendor = allVendors.find((v) => v.vendor_id === sel.vendor_id);
    return {
      vendor_id: sel.vendor_id,
      company_name: vendor?.company_name ?? 'Unknown',
      contact_name: vendor?.primary_contact?.full_name ?? '\u2014',
      contact_email: vendor?.primary_contact?.email ?? '\u2014',
    };
  });

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="Deadline" value={formatDeadline(data.deadline)} />
        <SummaryCard label="Template" value={templateName} />
        <SummaryCard label="Documents" value={`${(data.documentIds ?? []).length}`} />
        <SummaryCard label="Vendors" value={`${data.vendorSelections.length}`} />
      </div>

      {/* Instructions (if provided) */}
      {data.instructions.trim() && (
        <Card>
          <div className="p-6">
            <h3 className="mb-2 text-sm font-semibold text-secondary-900">Instructions to Vendors</h3>
            <p className="whitespace-pre-line rounded-md bg-secondary-50 p-3 text-sm text-secondary-700">
              {data.instructions.trim()}
            </p>
          </div>
        </Card>
      )}

      {/* Vendor List */}
      <Card>
        <div className="p-6">
          <h3 className="mb-4 text-sm font-semibold text-secondary-900">Selected Vendors</h3>
          <Table<VendorRow>
            columns={vendorColumns}
            data={vendorRows}
            keyExtractor={(row) => row.vendor_id}
            mobileTitle="company_name"
          />
        </div>
      </Card>

      {/* Footer */}
      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack} disabled={isSubmitting}>
          Back
        </Button>
        <Button onClick={() => setShowConfirm(true)} disabled={isSubmitting}>
          Send Invitations
        </Button>
      </div>

      {/* Confirmation Modal */}
      <Modal
        isOpen={showConfirm}
        onClose={() => !isSubmitting && setShowConfirm(false)}
        title="Send Bid Invitations"
        size="sm"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setShowConfirm(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                onSubmit();
              }}
              isLoading={isSubmitting}
            >
              Send {data.vendorSelections.length} Invitation
              {data.vendorSelections.length !== 1 ? 's' : ''}
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Send bid invitations to{' '}
          <strong>{data.vendorSelections.length} vendors</strong> for{' '}
          <strong>{task.name}</strong>?
        </p>
        <p className="mt-2 text-sm text-secondary-500">
          This will email each vendor a unique bid portal link. This action cannot be undone.
        </p>
      </Modal>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <div className="p-4">
        <p className="text-xs font-medium text-secondary-500">{label}</p>
        <p className="mt-1 truncate text-sm font-semibold text-secondary-900">{value}</p>
      </div>
    </Card>
  );
}
