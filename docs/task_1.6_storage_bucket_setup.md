# Task 1.6 — Supabase Storage Bucket Setup Guide

**Project:** BluOnX Bid Management & Vendor Coordination System  
**Last Updated:** September 9, 2026

---

## Three Buckets to Create

All buckets are **private**. Create via **Supabase Dashboard → Storage → New Bucket**, with the **default** settings: leave the MIME-type field and the file size limit alone. Both are set by `database/storage_rls_policies.sql` (its BUCKET CONFIGURATION block), which is the source of truth for bucket config; the limits below are what that script applies.

| Bucket Name | Purpose | Allowed extensions | File Size Limit |
|---|---|---|---|
| `vendor-documents` | W-9, insurance certs, master trade agreements | `.pdf .jpg .jpeg .png .doc .docx` | Dev: 50 MB · Prod: 200 MB |
| `project-documents` | Civil plans, drawings, specs, site photos, budgets, notes | `.pdf .jpg .jpeg .png .tif .tiff .txt .doc .docx .xls .xlsx .dwg .dxf .dwf .dgn` | Dev: 50 MB · Prod: 200 MB |
| `bid-attachments` | Docs vendors upload with bid submissions | `.pdf .jpg .jpeg .png` | 10 MB (all environments) |

> **Validation is extension-first** (see `backend/app/core/file_validation.py`). The allow-list above is by **extension**; declared MIME is advisory. A generic/blank type or `application/octet-stream` is trusted (CAD `.dwg/.dxf/.dwf/.dgn` and some Office files arrive that way), while a specific content-type that contradicts the extension is rejected. Magic bytes are checked by extension where a signature exists (PDF/image/TIFF, ZIP for `.docx/.xlsx`, OLE for `.doc/.xls`, `AC10` for `.dwg`); `.txt/.dxf/.dwf/.dgn` have none and pass on extension alone. The Supabase bucket-level MIME allow-list is left **unset (NULL) on all three buckets**, because app-layer validation is the gate. `storage_rls_policies.sql` sets it to NULL explicitly; do not set it by hand in the Dashboard. A bucket list narrower than the extension allow-list above is the exact defect this replaced: `.docx/.xlsx/.dwg` uploads passed validation here and then failed at storage as an opaque 500.

---

## Folder Path Conventions

Entity UUIDs are used as top-level folders (the "coat check" pattern).

| Bucket | Path Pattern | DB Table |
|---|---|---|
| `vendor-documents` | `{vendor_id}/{document_type}/{filename}` | `vendor_documents.file_path` |
| `project-documents` | `{project_id}/{filename}` | `project_documents.file_path` |
| `bid-attachments` | `{bid_submission_id}/{filename}` | `bid_attachments.file_path` |

---

## RLS Policies

Run `storage_rls_policies.sql` in SQL Editor **after** creating the buckets. It does two things:
its BUCKET CONFIGURATION block sets `allowed_mime_types` (NULL) and `file_size_limit` on all three
buckets, then it creates 12 policies (4 ops × 3 buckets).

**Access model:**
- **Admin / PM** → authenticated role, governed by these RLS policies
- **Vendors** → all access goes through FastAPI using `service_role` key (bypasses RLS)
- **Anonymous** → zero access

---

## Verification

```sql
SELECT policyname, cmd
  FROM pg_policies
 WHERE schemaname = 'storage' AND tablename = 'objects'
 ORDER BY policyname;
```

Expected: 12 rows. Then upload/delete a test file in any bucket via the Dashboard.

---

## Free Tier vs Production

| | Free Tier (Dev) | Pro Plan (Prod) |
|---|---|---|
| Max file size | 50 MB (hard cap) | Up to 5 GB (configurable) |
| `bid-attachments` per file | 10 MB | 10 MB (product rule, not a plan limit) |
| Total storage | 1 GB | 100 GB included |
| Global file limit | Set in Storage Settings | Increase to 200+ MB |

**Production checklist:**
1. Upgrade to Pro plan
2. Increase global file size limit in **Storage → Settings**
3. Create the 3 buckets in the production project with **default** settings (private, no MIME list, no size limit set by hand)
4. Run `storage_rls_policies.sql` in the production SQL Editor, substituting the **PRODUCTION** `UPDATE storage.buckets` pair (commented out near the top of that file) for the DEV pair. Do **not** configure the buckets by hand, which is how the config drifted before.
5. Verify with the query above, plus the `storage.buckets` query at the bottom of `storage_rls_policies.sql`
