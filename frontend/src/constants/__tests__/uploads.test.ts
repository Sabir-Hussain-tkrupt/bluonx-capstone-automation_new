import { describe, it, expect } from 'vitest';
import {
  BID_ATTACHMENT_ACCEPT,
  BID_ATTACHMENT_MAX_MB,
  PROJECT_DOCUMENT_ACCEPT,
  PROJECT_DOCUMENT_MAX_MB,
  VENDOR_DOCUMENT_ACCEPT,
  VENDOR_DOCUMENT_MAX_MB,
} from '../uploads';

function tokens(accept: string): string[] {
  return accept.split(',').map((t) => t.trim());
}

const ALL = {
  'vendor-documents': VENDOR_DOCUMENT_ACCEPT,
  'project-documents': PROJECT_DOCUMENT_ACCEPT,
  'bid-attachments': BID_ATTACHMENT_ACCEPT,
};

describe('upload accept lists', () => {
  it('mirrors BUCKET_CONFIGS.allowed_extensions for every bucket', () => {
    // These are the backend's allowed_extensions sets, transcribed. The backend
    // is the gate; a list narrower here silently blocks a file the server would
    // have taken, with no error the user can see.
    expect(tokens(VENDOR_DOCUMENT_ACCEPT).sort()).toEqual(
      ['.doc', '.docx', '.jpeg', '.jpg', '.pdf', '.png'].sort(),
    );
    expect(tokens(PROJECT_DOCUMENT_ACCEPT).sort()).toEqual(
      [
        '.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff',
        '.txt', '.doc', '.docx', '.xls', '.xlsx',
        '.dwg', '.dxf', '.dwf', '.dgn',
      ].sort(),
    );
    expect(tokens(BID_ATTACHMENT_ACCEPT).sort()).toEqual(
      ['.pdf', '.jpg', '.jpeg', '.png'].sort(),
    );
  });

  it('has 15 project-document extensions, including all four CAD types', () => {
    const project = tokens(PROJECT_DOCUMENT_ACCEPT);
    expect(project).toHaveLength(15);
    expect(project).toEqual(expect.arrayContaining(['.dwg', '.dxf', '.dwf', '.dgn']));
  });

  it('uses only extension tokens, never MIME tokens', () => {
    // FileUpload's isAcceptedType demands an exact file.type match for a MIME
    // token, so a PDF the browser labels application/octet-stream is rejected.
    // That was the bid-attachments bug; extension tokens ignore file.type.
    for (const [bucket, accept] of Object.entries(ALL)) {
      for (const token of tokens(accept)) {
        expect(`${bucket}: ${token}`).toBe(`${bucket}: ${token.toLowerCase()}`);
        expect(token.startsWith('.'), `${bucket} token ${token}`).toBe(true);
        expect(token.includes('/'), `${bucket} token ${token}`).toBe(false);
      }
    }
  });

  it('keeps both spellings of the two-spelling extensions', () => {
    // .tiff shipped without .tif on the SoW input, so a .tif scope of work was
    // unselectable. Keep each pair together.
    const project = tokens(PROJECT_DOCUMENT_ACCEPT);
    expect(project).toEqual(expect.arrayContaining(['.tif', '.tiff']));
    expect(project).toEqual(expect.arrayContaining(['.jpg', '.jpeg']));
    for (const accept of Object.values(ALL)) {
      const t = tokens(accept);
      expect(t.includes('.jpg')).toBe(t.includes('.jpeg'));
    }
  });

  it('caps match the backend max_size_bytes for each bucket', () => {
    expect(VENDOR_DOCUMENT_MAX_MB).toBe(50);
    expect(PROJECT_DOCUMENT_MAX_MB).toBe(50);
    // vendor_portal.py MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024.
    expect(BID_ATTACHMENT_MAX_MB).toBe(10);
  });
});
