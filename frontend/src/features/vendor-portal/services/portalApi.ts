/**
 * Vendor portal API — thin router.
 *
 * Reads `import.meta.env.VITE_DEMO_MODE` at module load and dispatches
 * every call to either the in-memory mock (`portalApi.mock.ts`) or
 * the real Axios implementation (`portalApi.real.ts`). Both impls
 * satisfy the `PortalApi` interface, so the two cannot drift without
 * a compile error.
 *
 * All existing callers continue to import the same named exports from
 * this file — the split is invisible to them.
 */

import { mockPortalApi } from './portalApi.mock';
import { realPortalApi } from './portalApi.real';
import type { PortalApi } from './portalApi.types';

const USE_MOCK = import.meta.env.VITE_DEMO_MODE === 'true';
const impl: PortalApi = USE_MOCK ? mockPortalApi : realPortalApi;

// Arrow wrappers (not bare re-exports) preserve `this` binding to the
// chosen impl object and keep the types sharp at each call site.
export const setVendorJwt: PortalApi['setVendorJwt'] = (token) => impl.setVendorJwt(token);
export const getVendorJwt: PortalApi['getVendorJwt'] = () => impl.getVendorJwt();
export const setAuthFailureHandler: PortalApi['setAuthFailureHandler'] = (fn) =>
  impl.setAuthFailureHandler(fn);

export const validateToken: PortalApi['validateToken'] = (token) => impl.validateToken(token);

export const createDraft: PortalApi['createDraft'] = (payload) => impl.createDraft(payload);
export const updateDraft: PortalApi['updateDraft'] = (id, payload) =>
  impl.updateDraft(id, payload);

export const submitBid: PortalApi['submitBid'] = (submissionId) => impl.submitBid(submissionId);

export const uploadAttachment: PortalApi['uploadAttachment'] = (submissionId, file) =>
  impl.uploadAttachment(submissionId, file);
export const deleteAttachment: PortalApi['deleteAttachment'] = (submissionId, attachmentId) =>
  impl.deleteAttachment(submissionId, attachmentId);

export const downloadProjectDocument: PortalApi['downloadProjectDocument'] = (documentId) =>
  impl.downloadProjectDocument(documentId);

export type { DraftPayload } from './portalApi.types';
