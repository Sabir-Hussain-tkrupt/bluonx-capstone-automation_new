import { describe, it, expect } from 'vitest';
import { normalizeSignature, signatureMatches } from '../attestation';

describe('normalizeSignature', () => {
  it('trims, collapses internal whitespace, and uppercases', () => {
    expect(normalizeSignature('  Acme   Grading  ')).toBe('ACME GRADING');
  });
});

describe('signatureMatches', () => {
  const company = 'Acme Grading';

  it('matches the exact company name', () => {
    expect(signatureMatches('Acme Grading', company)).toBe(true);
  });

  it('is case-insensitive', () => {
    expect(signatureMatches('acme grading', company)).toBe(true);
    expect(signatureMatches('ACME GRADING', company)).toBe(true);
  });

  it('tolerates surrounding and repeated whitespace', () => {
    expect(signatureMatches('  ACME   GRADING ', company)).toBe(true);
  });

  it('rejects an empty signature', () => {
    expect(signatureMatches('', company)).toBe(false);
    expect(signatureMatches('   ', company)).toBe(false);
  });

  it('rejects a different name', () => {
    expect(signatureMatches('Acme', company)).toBe(false);
    expect(signatureMatches('Summit Grading', company)).toBe(false);
  });

  it('does not silently pass on punctuation differences', () => {
    // Punctuation is significant — "Acme Grading, LLC" is a different string.
    expect(signatureMatches('Acme Grading, LLC', company)).toBe(false);
  });
});
