import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { DatePicker } from '@/components/ui/DatePicker';
import { FileUpload } from '@/components/ui/FileUpload';
import { useToast } from '@/components/ui/Toast/useToast';
import { useUploadVendorDocument } from '@/features/vendors/hooks/useVendorDocuments';
import type { VendorDocument } from '@/features/vendors/api/vendor.queries';

const DOC_TYPE_OPTIONS = [
  { value: 'w9', label: 'W-9' },
  { value: 'insurance_certificate', label: 'Insurance Certificate' },
  { value: 'master_trade_agreement', label: 'Master Trade Agreement' },
];

interface VendorDocumentUploadProps {
  vendorId: string;
  isOpen: boolean;
  onClose: () => void;
  existingDocuments?: VendorDocument[];
}

export function VendorDocumentUpload({
  vendorId,
  isOpen,
  onClose,
  existingDocuments,
}: VendorDocumentUploadProps) {
  const { toast } = useToast();
  const uploadMutation = useUploadVendorDocument();

  const [documentType, setDocumentType] = useState('');
  const [expirationDate, setExpirationDate] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');

  const isInsurance = documentType === 'insurance_certificate';
  const canSubmit = documentType && selectedFile && (!isInsurance || expirationDate);
  const hasExistingValidInsurance = (existingDocuments ?? []).some(
    (doc) => doc.document_type === 'insurance_certificate' && doc.status === 'valid',
  );
  const showSupersedeHint = isInsurance && hasExistingValidInsurance;

  const resetForm = () => {
    setDocumentType('');
    setExpirationDate('');
    setSelectedFile(null);
    setFileError('');
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = () => {
    if (!selectedFile || !documentType) return;

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('document_type', documentType);
    if (expirationDate) {
      formData.append('expiration_date', expirationDate);
    }

    uploadMutation.mutate(
      { vendorId, formData },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Document uploaded successfully.' });
          handleClose();
        },
        onError: (error) => {
          const msg = (error as { message?: string })?.message ?? 'Failed to upload document.';
          toast({ variant: 'danger', message: msg });
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Upload Document"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={uploadMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            isLoading={uploadMutation.isPending}
            disabled={!canSubmit}
          >
            Upload
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-secondary-700">
            Document Type <span className="text-danger-500">*</span>
          </label>
          <Select
            options={DOC_TYPE_OPTIONS}
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            placeholder="Select document type"
          />
        </div>

        {isInsurance && (
          <div>
            <label className="mb-1 block text-sm font-medium text-secondary-700">
              Expiration Date <span className="text-danger-500">*</span>
            </label>
            <DatePicker
              value={expirationDate}
              onChange={(e) => setExpirationDate(e.target.value)}
              minDate={new Date().toISOString().split('T')[0]}
            />
            {showSupersedeHint && (
              <p className="mt-1 text-sm text-secondary-500" data-testid="supersede-hint">
                This will become the active certificate. The previous one will remain on file as a historical record.
              </p>
            )}
          </div>
        )}

        <div>
          <label className="mb-1 block text-sm font-medium text-secondary-700">
            File <span className="text-danger-500">*</span>
          </label>
          <FileUpload
            accept=".pdf,.jpg,.jpeg,.png"
            maxSizeMB={50}
            onFilesSelected={(files) => {
              setSelectedFile(files[0] ?? null);
              setFileError('');
            }}
            onError={setFileError}
            error={fileError}
            uploading={uploadMutation.isPending}
            hint="PDF, JPEG, or PNG up to 50MB"
            onRemoveFile={() => setSelectedFile(null)}
          />
        </div>
      </div>
    </Modal>
  );
}
