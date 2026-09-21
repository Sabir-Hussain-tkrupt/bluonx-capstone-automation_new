/**
 * Client-side upload accept lists and size caps.
 *
 * These mirror `BUCKET_CONFIGS` in `backend/app/core/file_validation.py`, which
 * is the actual gate. Everything here is a pre-flight courtesy: it saves a
 * round-trip on a file the server would refuse anyway. That makes the failure
 * mode asymmetric and worth spelling out:
 *
 *   - A list WIDER than the backend's is harmless. The upload is attempted and
 *     the server returns a 422 the user can read.
 *   - A list NARROWER than the backend's is invisible. The OS file picker
 *     filters the file out, so the user cannot select it and is told nothing.
 *     That is exactly how a .dwg scope of work became unpickable.
 *
 * So when the backend's allowed_extensions changes, change these too.
 *
 * Always EXTENSION tokens, never MIME tokens. `isAcceptedType` in
 * `components/ui/FileUpload` requires an exact `file.type` match for a MIME
 * token, and browsers routinely report CAD and Office files, and sometimes even
 * PDFs, as `application/octet-stream`. An extension token ignores `file.type`
 * entirely, which is the behaviour every upload surface here wants.
 */

/** Common document extensions: PDF, Images, Word, Excel, PowerPoint, TXT */
export const COMMON_DOCUMENT_EXTENSIONS =
  '.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg,.tif,.tiff,.txt,.doc,.docx,.xls,.xlsx,.ppt,.pptx';

/** vendor-documents: W-9, insurance certificates, master trade agreements. */
export const VENDOR_DOCUMENT_ACCEPT = COMMON_DOCUMENT_EXTENSIONS;
export const VENDOR_DOCUMENT_MAX_MB = 50;
export const VENDOR_DOCUMENT_HINT =
  'PDF, Images, Office (Word/Excel/PowerPoint), or TXT up to 50MB';

/** project-documents: plans, specs, budgets, notes, Office, and CAD. */
export const PROJECT_DOCUMENT_ACCEPT = `${COMMON_DOCUMENT_EXTENSIONS},.dwg,.dxf,.dwf,.dgn`;
export const PROJECT_DOCUMENT_MAX_MB = 50;
export const PROJECT_DOCUMENT_HINT =
  'PDF, Images, Office (Word/Excel/PowerPoint), TXT, or CAD (DWG/DXF/DWF/DGN) up to 50MB';

/**
 * bid-attachments: documents a vendor sends with a bid.
 */
export const BID_ATTACHMENT_ACCEPT = COMMON_DOCUMENT_EXTENSIONS;
export const BID_ATTACHMENT_MAX_MB = 10;
export const BID_ATTACHMENT_HINT =
  'PDF, Images, Office (Word/Excel/PowerPoint), or TXT up to 10MB each';
