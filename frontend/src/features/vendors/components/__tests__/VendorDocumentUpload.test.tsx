import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { VendorDocumentUpload } from '../VendorDocumentUpload';
import type { VendorDocument } from '@/features/vendors/api/vendor.queries';

vi.mock('@/features/vendors/hooks/useVendorDocuments', () => ({
  useUploadVendorDocument: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

const HINT_TEXT = /This will become the active certificate/i;

function makeDoc(overrides: Partial<VendorDocument>): VendorDocument {
  return {
    id: 'doc-1',
    vendor_id: 'v-1',
    document_type: 'insurance_certificate',
    file_name: 'cert.pdf',
    file_path: 'v-1/insurance_certificate/cert.pdf',
    file_size: 1024,
    expiration_date: '2027-01-01',
    status: 'valid',
    uploaded_by: 'u-1',
    uploaded_at: '2026-05-25T00:00:00Z',
    updated_at: '2026-05-25T00:00:00Z',
    ...overrides,
  };
}

function selectDocumentType(value: string) {
  // The Select component renders a native <select>; change its value.
  const selects = document.querySelectorAll('select');
  // The first select in the modal is the document_type select.
  const docTypeSelect = selects[0] as HTMLSelectElement;
  fireEvent.change(docTypeSelect, { target: { value } });
}

describe('VendorDocumentUpload — supersede hint', () => {
  it('shows hint when type is insurance and a valid insurance cert already exists', () => {
    renderWithRouter(
      <VendorDocumentUpload
        vendorId="v-1"
        isOpen={true}
        onClose={() => {}}
        existingDocuments={[makeDoc({ status: 'valid' })]}
      />,
    );
    selectDocumentType('insurance_certificate');
    expect(screen.getByText(HINT_TEXT)).toBeInTheDocument();
  });

  it('hides hint when type is insurance but no valid existing insurance cert', () => {
    renderWithRouter(
      <VendorDocumentUpload
        vendorId="v-1"
        isOpen={true}
        onClose={() => {}}
        existingDocuments={[makeDoc({ status: 'expired' })]}
      />,
    );
    selectDocumentType('insurance_certificate');
    expect(screen.queryByText(HINT_TEXT)).not.toBeInTheDocument();
  });

  it('hides hint when document type is not insurance, even with existing insurance certs', () => {
    renderWithRouter(
      <VendorDocumentUpload
        vendorId="v-1"
        isOpen={true}
        onClose={() => {}}
        existingDocuments={[makeDoc({ status: 'valid' })]}
      />,
    );
    selectDocumentType('w9');
    expect(screen.queryByText(HINT_TEXT)).not.toBeInTheDocument();
  });

  it('hides hint when existingDocuments prop is omitted', () => {
    renderWithRouter(
      <VendorDocumentUpload
        vendorId="v-1"
        isOpen={true}
        onClose={() => {}}
      />,
    );
    selectDocumentType('insurance_certificate');
    expect(screen.queryByText(HINT_TEXT)).not.toBeInTheDocument();
  });
});
