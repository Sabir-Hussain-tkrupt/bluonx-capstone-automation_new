# Document Upload — Task 3.4 Reference

**Last Updated:** March 26, 2026

---

## Storage Buckets

| Bucket | Purpose | Path Pattern | Allowed Types | Max Size (Dev) |
|--------|---------|-------------|---------------|----------------|
| `vendor-documents` | W-9, insurance certs, MTAs | `{vendor_id}/{document_type}/{uuid}/{filename}` | PDF, JPEG, PNG, Word (DOC/DOCX) | 50 MB |
| `project-documents` | Civil plans, drawings, specs, photos | `{project_id}/{uuid}/{filename}` | PDF, JPEG, PNG, TIFF, TXT, Word (DOC/DOCX), Excel (XLS/XLSX), CAD (DWG/DXF/DWF/DGN) | 50 MB |
| `bid-attachments` | Vendor bid submission docs | `{bid_submission_id}/{filename}` | PDF, JPEG, PNG | 50 MB |

> `bid-attachments` endpoints will be wired in Phase 5. The reusable components are ready.

---

## Vendor Document Types

| Type | Label | Expiration Required | Notes |
|------|-------|:-------------------:|-------|
| `w9` | W-9 | No | Federal tax form |
| `insurance_certificate` | Insurance Certificate | Yes | Also updates `vendors.insurance_expiration_date` |
| `master_trade_agreement` | Master Trade Agreement | No | Signed MTA |

Document statuses: `valid` (default on upload), `expired`, `pending_review`.

---

## API Endpoints

### Vendor Documents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/vendors/{id}/documents` | List vendor documents |
| `POST` | `/v1/vendors/{id}/documents` | Upload (multipart/form-data: `file`, `document_type`, `expiration_date`) |
| `GET` | `/v1/vendors/{id}/documents/{doc_id}/url` | Signed download URL (1hr expiry) |
| `DELETE` | `/v1/vendors/{id}/documents/{doc_id}` | Delete from storage + DB |

### Project Documents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/projects/{id}/documents` | List project documents |
| `POST` | `/v1/projects/{id}/documents` | Upload (multipart/form-data: `file`) |
| `GET` | `/v1/projects/{id}/documents/{doc_id}/url` | Signed download URL (1hr expiry) |
| `DELETE` | `/v1/projects/{id}/documents/{doc_id}` | Delete from storage + DB |

---

## Validation

- **Server-side (extension-first)**: file size check, extension allow-list (the primary gate), an advisory content-type check (a generic/blank or `application/octet-stream` type is trusted, since CAD/Office files often arrive that way; a *specific* type that contradicts the extension is rejected), and magic-byte verification keyed by extension (PDF/image/TIFF, ZIP for `.docx`/`.xlsx`, OLE for `.doc`/`.xls`, `AC10` for `.dwg`; `.txt`/`.dxf`/`.dwf`/`.dgn` have no signature and validate on extension alone)
- **Client-side**: File size and extension pre-check before upload (the `accept` list on each upload mirrors its bucket)
- Invalid uploads return `422` with a descriptive error message

---

## Signed URLs

- Generated on-demand via the `/url` endpoint
- Expire after **1 hour**
- Files are never served directly — always through signed URLs
