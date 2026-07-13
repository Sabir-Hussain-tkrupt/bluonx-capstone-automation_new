/**
 * Scope of Work attestation "signature" matching.
 *
 * The vendor signs by typing their company name. We accept it as a signature
 * only when it matches the vendor's on-file company name. Matching is lenient
 * about the things humans get wrong when retyping a name — surrounding and
 * repeated whitespace, and letter case — but nothing else.
 *
 * NOTE: this is a client-side gate only (for now). The backend submit
 * validator remains the authority for the presence/CAPS rules.
 */

/** trim → collapse internal whitespace → uppercase. */
export function normalizeSignature(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toUpperCase();
}

/** True when the typed signature matches the vendor's company name. */
export function signatureMatches(typed: string, companyName: string): boolean {
  const t = normalizeSignature(typed);
  return t.length > 0 && t === normalizeSignature(companyName);
}
