import { z } from 'zod';

/**
 * Single source of truth for email validation.
 *
 * There were three: a zod `.email()` in ContactForm, a hand-rolled regex in
 * the CSV importer, and nothing at all in the inline contact adder on the
 * create form. That last gap let a malformed address reach the API, where
 * Pydantic's EmailStr rejected it with a 422 that the axios interceptor
 * flattens into a generic "check your input" with no field named.
 *
 * Trims first so a pasted address with trailing whitespace validates.
 */
export const emailSchema = z.string().trim().email('Enter a valid email address');

/** Boolean form, for non-zod call sites such as per-row CSV validation. */
export function isValidEmail(value: string): boolean {
  return emailSchema.safeParse(value).success;
}
