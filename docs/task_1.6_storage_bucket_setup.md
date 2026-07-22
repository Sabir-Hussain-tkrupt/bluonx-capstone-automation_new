# Task 1.6 — Supabase Storage Bucket Setup Guide

**Project:** BluOnX Bid Management & Vendor Coordination System  
**Last Updated:** February 24, 2026

---

## Three Buckets to Create

All buckets are **private**. Create via **Supabase Dashboard → Storage → New Bucket**.

| Bucket Name | Purpose | Allowed extensions | File Size Limit |
|---|---|---|---|
| `vendor-documents` | W-9, insurance certs, master trade agreements | `.pdf .jpg .jpeg .png .doc .docx` | Dev: 50 MB · Prod: 200 MB |
| `project-documents` | Civil plans, drawings, specs, site photos, budgets, notes | `.pdf .jpg .jpeg .png .tif .tiff .txt .doc .docx .xls .xlsx .dwg .dxf .dwf .dgn` | Dev: 50 MB · Prod: 200 MB |
| `bid-attachments` | Docs vendors upload with bid submissions | `.pdf .jpg .jpeg .png` | Dev: 50 MB · Prod: 200 MB |

> **Validation is extension-first** (see `backend/app/core/file_validation.py`). The allow-list above is by **extension**; declared MIME is advisory. A generic/blank type or `application/octet-stream` is trusted (CAD `.dwg/.dxf/.dwf/.dgn` and some Office files arrive that way), while a specific content-type that contradicts the extension is rejected. Magic bytes are checked by extension where a signature exists (PDF/image/TIFF, ZIP for `.docx/.xlsx`, OLE for `.doc/.xls`, `AC10` for `.dwg`); `.txt/.dxf/.dwf/.dgn` have none and pass on extension alone. The Supabase bucket-level MIME allow-list (Dashboard) should be left permissive or unset for `project-documents`, since app-layer validation is the gate.

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

Run `storage_rls_policies.sql` in SQL Editor **after** creating the buckets. Creates 12 policies (4 ops × 3 buckets).

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
| Total storage | 1 GB | 100 GB included |
| Global file limit | Set in Storage Settings | Increase to 200+ MB |

**Production checklist:**
1. Upgrade to Pro plan
2. Increase global file size limit in **Storage → Settings**
3. Re-create the 3 buckets with production file size limits
4. Run `storage_rls_policies.sql` in production SQL Editor
5. Verify with the query above
