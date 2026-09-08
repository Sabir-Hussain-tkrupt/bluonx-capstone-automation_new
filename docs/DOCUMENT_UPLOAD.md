# Document Upload — Task 3.4 Reference

**Last Updated:** September 9, 2026

---

## Storage Buckets

| Bucket | Purpose | Path Pattern |
|--------|---------|-------------|
| `vendor-documents` | W-9, insurance certs, MTAs | `{vendor_id}/{document_type}/{uuid}/{filename}` |
| `project-documents` | Civil plans, drawings, specs, photos | `{project_id}/{uuid}/{filename}` |
| `bid-attachments` | Vendor bid submission docs | `{bid_submission_id}/{filename}` |

**Allowed types and size limits are deliberately not listed here.** They live in exactly two
places, and duplicating them into this doc is what let them drift:

- **Per-bucket allowed extensions and max size**: `BUCKET_CONFIGS` in
  [`backend/app/core/file_validation.py`](../backend/app/core/file_validation.py). This is the
  single gate; the Supabase buckets carry no MIME allow-list of their own.
- **Bucket provisioning** (creation, `file_size_limit`, dev vs prod):
  [`task_1.6_storage_bucket_setup.md`](task_1.6_storage_bucket_setup.md) and the BUCKET
  CONFIGURATION block in `database/storage_rls_policies.sql`.

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

### Bid Attachments (vendor portal)

Live. Vendor-authenticated (custom JWT), not Supabase Auth. See the Vendor Portal Boundary
in `CLAUDE.md`. Handlers in `backend/app/routers/vendor_portal.py`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/vendor-portal/submissions/{id}/attachments` | Upload one attachment to a draft submission |
| `DELETE` | `/v1/vendor-portal/submissions/{id}/attachments/{attachment_id}` | Remove an attachment |

Per-attachment cap is `MAX_ATTACHMENT_BYTES`; per-submission caps
(`MAX_ATTACHMENTS_PER_SUBMISSION`, `MAX_ATTACHMENT_TOTAL_BYTES`) live in
`backend/app/services/vendor_portal_service.py`.

---

## Validation

- **Server-side (extension-first)**: file size check, extension allow-list (the primary gate), an advisory content-type check (a generic/blank or `application/octet-stream` type is trusted, since CAD/Office files often arrive that way; a *specific* type that contradicts the extension is rejected), and magic-byte verification keyed by extension (PDF/image/TIFF, ZIP for `.docx`/`.xlsx`, OLE for `.doc`/`.xls`, `AC10` for `.dwg`; `.txt`/`.dxf`/`.dwf`/`.dgn` have no signature and validate on extension alone)
- **Client-side**: File size and extension pre-check before upload (the `accept` list on each upload mirrors its bucket)
- Invalid uploads return `422` with a descriptive error message
- A rejection from the **storage layer** (rather than the validator) returns the storage API's
  own status (`415` unsupported type, `413` too large, `409` duplicate, `400` otherwise) with
  its reason in `detail` (`upload_file` in `backend/app/core/storage.py`). Only genuine storage
  failures (network, auth, quota) are a `500`.

---

## Signed URLs

- Generated on-demand via the `/url` endpoint
- Expire after **1 hour**
- Files are never served directly — always through signed URLs
