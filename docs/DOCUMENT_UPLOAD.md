# Document Upload — Task 3.4 Reference

**Last Updated:** March 26, 2026

---

## Storage Buckets

| Bucket | Purpose | Path Pattern | Allowed Types | Max Size (Dev) |
|--------|---------|-------------|---------------|----------------|
| `vendor-documents` | W-9, insurance certs, MTAs | `{vendor_id}/{document_type}/{filename}` | PDF, JPEG, PNG | 50 MB |
| `project-documents` | Civil plans, drawings, specs, photos | `{project_id}/{filename}` | PDF, JPEG, PNG, TIFF | 50 MB |
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

- **Server-side**: MIME type check, file size check, extension-to-MIME consistency, magic byte verification
- **Client-side**: File size and extension pre-check before upload
- Invalid uploads return `422` with a descriptive error message

---

## Signed URLs

- Generated on-demand via the `/url` endpoint
- Expire after **1 hour**
- Files are never served directly — always through signed URLs
