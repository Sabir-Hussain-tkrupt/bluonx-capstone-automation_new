# Task 1.6 — Supabase Storage Bucket Setup Guide

**Project:** BluOnX Bid Management & Vendor Coordination System  
**Last Updated:** February 24, 2026

---

## Three Buckets to Create

All buckets are **private**. Create via **Supabase Dashboard → Storage → New Bucket**.

| Bucket Name | Purpose | MIME Types | File Size Limit |
|---|---|---|---|
| `vendor-documents` | W-9, insurance certs, master trade agreements | `application/pdf`, `image/jpeg`, `image/png` | Dev: 50 MB · Prod: 200 MB |
| `project-documents` | Civil plans, drawings, specs, site photos | `application/pdf`, `image/jpeg`, `image/png`, `image/tiff` | Dev: 50 MB · Prod: 200 MB |
| `bid-attachments` | Docs vendors upload with bid submissions | `application/pdf`, `image/jpeg`, `image/png` | Dev: 50 MB · Prod: 200 MB |

> **DWG support:** If needed later, add `application/octet-stream` to `project-documents` MIME types (DWG has no standardized MIME type).

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
