import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { FileUpload } from '@/components/ui/FileUpload';
import { FormField } from '@/components/ui/FormField';
import { TextInput } from '@/components/ui/TextInput';
import { DatePicker } from '@/components/ui/DatePicker';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { FINANCE_DOCUMENT_ACCEPT, FINANCE_DOCUMENT_HINT, FINANCE_DOCUMENT_MAX_MB } from '@/constants/uploads';
import { parseMoneyInput } from '@/features/budgets/utils/money';
import { useUploadInvoice } from '../hooks/useInvoices';

interface InvoiceUploadModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function InvoiceUploadModal({ projectId, isOpen, onClose }: InvoiceUploadModalProps) {
  const { toast } = useToast();
  const upload = useUploadInvoice(projectId);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [payee, setPayee] = useState('');
  const [number, setNumber] = useState('');
  const [date, setDate] = useState('');
  const [amount, setAmount] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setFileError('');
    setPayee('');
    setNumber('');
    setDate('');
    setAmount('');
    setErrors({});
    setSubmitError(null);
  };

  const close = () => {
    if (upload.isPending) return;
    reset();
    onClose();
  };

  const submit = () => {
    const next: Record<string, string> = {};
    const parsed = parseMoneyInput(amount);
    if (!parsed || Number(parsed) <= 0) next.amount = 'Enter an amount greater than zero (at most 2 decimals).';
    if (!payee.trim()) next.payee = 'Enter who the invoice is from.';
    if (!file) next.file = 'Choose the invoice file.';
    setErrors(next);
    if (Object.keys(next).length || !file || !parsed) return;
    setSubmitError(null);
    upload.mutate(
      { file, amount: parsed, payee_name: payee.trim(), invoice_number: number.trim() || undefined, invoice_date: date || undefined },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Invoice uploaded. Categorise it to a T&M line to start approval.' });
          reset();
          onClose();
        },
        onError: (e) => setSubmitError(errorMessage(e, 'Could not upload the invoice.')),
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title="Upload invoice"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={upload.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={upload.isPending}>Upload</Button>
        </>
      }
    >
      <div className="space-y-4">
        {submitError && <Alert variant="danger" title="Could not upload invoice">{submitError}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Payee" htmlFor="invoice-payee" required error={errors.payee}>
            <TextInput id="invoice-payee" value={payee} onChange={(e) => setPayee(e.target.value)}
              placeholder="e.g. Smith & Lane Attorneys" error={errors.payee} autoFocus />
          </FormField>
          <FormField label="Amount" htmlFor="invoice-amount" required error={errors.amount}>
            <TextInput id="invoice-amount" value={amount} onChange={(e) => setAmount(e.target.value)}
              leftAddon="$" inputMode="decimal" className="tabular-nums" error={errors.amount} />
          </FormField>
          <FormField label="Invoice number" htmlFor="invoice-number">
            <TextInput id="invoice-number" value={number} onChange={(e) => setNumber(e.target.value)} />
          </FormField>
          <FormField label="Invoice date" htmlFor="invoice-date">
            <DatePicker id="invoice-date" value={date} onChange={(e) => setDate(e.target.value)} />
          </FormField>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-secondary-700">
            File <span className="text-danger-500">*</span>
          </label>
          <FileUpload
            accept={FINANCE_DOCUMENT_ACCEPT}
            maxSizeMB={FINANCE_DOCUMENT_MAX_MB}
            onFilesSelected={(files) => {
              setFile(files[0] ?? null);
              setFileError('');
            }}
            onError={setFileError}
            error={fileError || errors.file}
            uploading={upload.isPending}
            hint={FINANCE_DOCUMENT_HINT}
            onRemoveFile={() => setFile(null)}
          />
        </div>
      </div>
    </Modal>
  );
}
