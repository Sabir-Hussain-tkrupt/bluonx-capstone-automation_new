import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { VendorCSVImport } from '../VendorCSVImport';

interface ParseResult {
  data: Record<string, string>[];
  errors: { code?: string; message?: string; row?: number }[];
  meta: { fields?: string[] };
}

let parseResult: ParseResult;

vi.mock('papaparse', () => ({
  default: {
    parse: (_file: unknown, opts: { complete: (r: ParseResult) => void }) => {
      opts.complete(parseResult);
    },
  },
}));

const importMutateMock = vi.fn();

vi.mock('@/features/vendors/hooks/useImportVendors', () => ({
  useImportVendors: () => ({ mutate: importMutateMock, isPending: false }),
}));

function rowsFor(names: string[]) {
  return names.map((name, i) => ({ 'Company Name': name, City: `City${i}` }));
}

async function uploadFile() {
  renderWithRouter(<VendorCSVImport isOpen onClose={vi.fn()} />);
  // The modal renders through a portal, so the input is on document, not in
  // the render container.
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  fireEvent.change(input, {
    target: { files: [new File(['x'], 'vendors.csv', { type: 'text/csv' })] },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  parseResult = { data: [], errors: [], meta: { fields: [] } };
});

describe('VendorCSVImport row numbering', () => {
  it('reports server errors against the original CSV line, not the submitted index', async () => {
    // The regression: the preview numbered rows over the whole file, but only
    // valid rows were submitted and the server numbered its errors over the
    // array it received. With row 1 invalid, a server error on its first row
    // (really CSV row 2) was displayed as "Row 1", sending the user to edit
    // the wrong company.
    parseResult = {
      data: rowsFor(['', 'Beta', 'Gamma']), // row 1 has no company name
      errors: [],
      meta: { fields: ['Company Name', 'City'] },
    };
    importMutateMock.mockImplementation((_rows, opts) =>
      opts.onSuccess?.({
        created: 1,
        errors: [{ row: 1, message: "A vendor named 'Beta' already exists." }],
      }),
    );

    await uploadFile();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Confirm' }));
    await userEvent.click(screen.getByRole('button', { name: /Import 2 Vendor/ }));

    // Submitted [Beta, Gamma]; the server's "row 1" is Beta, on CSV line 2.
    expect(
      screen.getByText(/Row 2: A vendor named 'Beta' already exists\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Row 1:/)).not.toBeInTheDocument();
  });

  it('submits only the valid rows', async () => {
    parseResult = {
      data: rowsFor(['', 'Beta', 'Gamma']),
      errors: [],
      meta: { fields: ['Company Name', 'City'] },
    };
    importMutateMock.mockImplementation((_rows, opts) =>
      opts.onSuccess?.({ created: 2, errors: [] }),
    );

    await uploadFile();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Confirm' }));
    await userEvent.click(screen.getByRole('button', { name: /Import 2 Vendor/ }));

    const submitted = importMutateMock.mock.calls[0][0];
    expect(submitted).toHaveLength(2);
    expect(submitted.map((r: { company_name: string }) => r.company_name)).toEqual([
      'Beta',
      'Gamma',
    ]);
  });
});

describe('VendorCSVImport batch cap', () => {
  it('refuses a file over the row cap and says why', async () => {
    // Unbounded batches outran the client timeout while the server kept
    // creating vendors, so the user was told the import failed after it had
    // partly succeeded.
    parseResult = {
      data: rowsFor(Array.from({ length: 150 }, (_, i) => `Vendor ${i}`)),
      errors: [],
      meta: { fields: ['Company Name', 'City'] },
    };

    await uploadFile();

    expect(screen.getByText(/This file has 150 rows/)).toBeInTheDocument();
    expect(screen.getByText(/limited to 100 rows/)).toBeInTheDocument();
    // Never leaves the upload step.
    expect(
      screen.queryByRole('button', { name: 'Continue to Confirm' }),
    ).not.toBeInTheDocument();
  });

  it('accepts a file exactly at the cap', async () => {
    parseResult = {
      data: rowsFor(Array.from({ length: 100 }, (_, i) => `Vendor ${i}`)),
      errors: [],
      meta: { fields: ['Company Name', 'City'] },
    };

    await uploadFile();

    expect(screen.getByRole('button', { name: 'Continue to Confirm' })).toBeInTheDocument();
  });
});

describe('VendorCSVImport parse errors', () => {
  it('turns a malformed row into a row error rather than importing it', async () => {
    // A row with the wrong field count has shifted every value into the wrong
    // column, so importing it would create genuinely wrong records.
    parseResult = {
      data: rowsFor(['Alpha', 'Beta']),
      errors: [{ code: 'TooManyFields', message: 'Too many fields', row: 1 }],
      meta: { fields: ['Company Name', 'City'] },
    };

    await uploadFile();

    expect(screen.getByText(/Too many fields/)).toBeInTheDocument();

    // The malformed row is excluded, leaving only Alpha to import.
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Confirm' }));
    expect(screen.getByText('Ready to import 1 vendor(s)')).toBeInTheDocument();
    expect(screen.getByText('1 row(s) with errors will be skipped.')).toBeInTheDocument();
  });

  it('rejects a file whose delimiter could not be detected', async () => {
    parseResult = {
      data: rowsFor(['Alpha']),
      errors: [{ code: 'UndetectableDelimiter', message: 'nope' }],
      meta: { fields: ['Company Name', 'City'] },
    };

    await uploadFile();

    expect(screen.getByText(/column separator could not be detected/)).toBeInTheDocument();
  });

  it('rejects a file with duplicate column headers', async () => {
    parseResult = {
      data: [{ City: 'X' }],
      errors: [],
      meta: { fields: ['City', 'city'] },
    };

    await uploadFile();

    expect(screen.getByText(/share the same header/)).toBeInTheDocument();
  });
});
