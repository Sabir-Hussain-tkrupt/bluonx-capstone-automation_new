import { describe, it, expect } from 'vitest';
import type { AxiosError } from 'axios';
import { ApiError, errorMessage, fromSupabaseError, isApiError, normalizeAxiosError } from '../api';

type ErrorBody = { detail?: string; message?: string };

/** Minimal stand-in for the parts of an AxiosError that normalization reads. */
function axiosError(
  response?: { status: number; data?: ErrorBody | { detail: unknown } },
  opts: { hasRequest?: boolean; message?: string } = {},
): AxiosError<ErrorBody> {
  return {
    message: opts.message ?? 'Request failed',
    response,
    request: opts.hasRequest || response ? {} : undefined,
  } as unknown as AxiosError<ErrorBody>;
}

describe('ApiError', () => {
  it('is a real Error, so it carries a stack and survives instanceof', () => {
    const error = new ApiError('nope', 'CONFLICT', 409);

    // The whole point of the class: a thrown plain object has neither, which
    // is why every consumer used to cast its way back to this shape.
    expect(error).toBeInstanceOf(Error);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.stack).toBeTruthy();
    expect(error.name).toBe('ApiError');
    expect(error.message).toBe('nope');
    expect(error.code).toBe('CONFLICT');
    expect(error.status).toBe(409);
  });

  it('narrows with isApiError and rejects look-alike plain objects', () => {
    expect(isApiError(new ApiError('x', 'C', 409))).toBe(true);
    expect(isApiError({ message: 'x', code: 'C', status: 409 })).toBe(false);
    expect(isApiError(new Error('plain'))).toBe(false);
    expect(isApiError(undefined)).toBe(false);
  });
});

describe('normalizeAxiosError', () => {
  it.each([
    [400, 'BAD_REQUEST'],
    [409, 'CONFLICT'],
  ])('maps %i to %s and keeps the server detail', (status, code) => {
    const error = normalizeAxiosError(axiosError({ status, data: { detail: 'Server said no' } }));

    expect(error.status).toBe(status);
    expect(error.code).toBe(code);
    expect(error.message).toBe('Server said no');
  });

  it.each([
    [401, 'UNAUTHORIZED', 'Your session has expired. Please sign in again.'],
    [403, 'FORBIDDEN', 'You do not have permission to perform this action.'],
    [404, 'NOT_FOUND', 'The requested resource was not found.'],
    [500, 'SERVER_ERROR', 'A server error occurred. Please try again later.'],
  ])('replaces the server detail on %i with our own wording', (status, code, message) => {
    const error = normalizeAxiosError(axiosError({ status, data: { detail: 'raw server text' } }));

    expect(error.code).toBe(code);
    expect(error.message).toBe(message);
  });

  it('keeps a 422 detail that is a string', () => {
    // Our own services raise HTTPException(422, detail="…") with a specific
    // reason, e.g. a milestone date in the past. That text is the useful part.
    const error = normalizeAxiosError(
      axiosError({ status: 422, data: { detail: 'Milestone date cannot be in the past.' } }),
    );

    expect(error.code).toBe('VALIDATION_ERROR');
    expect(error.message).toBe('Milestone date cannot be in the past.');
  });

  it('falls back to generic wording when a 422 detail is an array', () => {
    // FastAPI's own request-validation 422s put an array of error objects in
    // `detail`. Rendering that verbatim would show "[object Object]".
    const error = normalizeAxiosError(
      axiosError({
        status: 422,
        data: { detail: [{ loc: ['body', 'email'], msg: 'field required' }] },
      }),
    );

    expect(error.message).toBe('Please check your input and try again.');
    expect(error.message).not.toContain('object Object');
  });

  it('reports an unreachable server as a network error', () => {
    const error = normalizeAxiosError(axiosError(undefined, { hasRequest: true }));

    expect(error.code).toBe('NETWORK_ERROR');
    expect(error.status).toBe(0);
    expect(error.message).toBe('Unable to reach the server. Check your connection.');
  });

  it('falls back to UNKNOWN_ERROR when the request never left', () => {
    const error = normalizeAxiosError(axiosError(undefined));

    expect(error.code).toBe('UNKNOWN_ERROR');
    expect(error.status).toBe(0);
  });

  it('always produces something the UI can narrow on', () => {
    const error = normalizeAxiosError(axiosError({ status: 503, data: { detail: 'down' } }));

    expect(isApiError(error)).toBe(true);
    expect(error.status).toBe(503);
    // No case for 503, so the code stays generic but the detail survives.
    expect(error.code).toBe('UNKNOWN_ERROR');
    expect(error.message).toBe('down');
  });
});

describe('fromSupabaseError', () => {
  it('wraps a Supabase error and defaults the status to 0', () => {
    const error = fromSupabaseError({ message: 'permission denied', code: '42501' });

    expect(isApiError(error)).toBe(true);
    expect(error.message).toBe('permission denied');
    expect(error.code).toBe('42501');
    expect(error.status).toBe(0);
  });

  it('takes a caller-supplied status, which is how PGRST116 becomes a 404', () => {
    const error = fromSupabaseError({ message: 'no rows', code: 'PGRST116' }, 404);

    expect(error.status).toBe(404);
  });

  it('labels a code-less error rather than leaving it undefined', () => {
    expect(fromSupabaseError({ message: 'boom' }).code).toBe('SUPABASE_ERROR');
  });
});

describe('errorMessage', () => {
  it('prefers the server message on an ApiError', () => {
    const error = new ApiError('This template is referenced by 2 bid packages.', 'CONFLICT', 409);

    expect(errorMessage(error, 'Failed.')).toBe('This template is referenced by 2 bid packages.');
  });

  it('reads a plain Error too, which covers Supabase auth failures', () => {
    expect(errorMessage(new Error('Invalid login credentials'), 'Failed.')).toBe(
      'Invalid login credentials',
    );
  });

  it('falls back for a non-Error, so internal junk never reaches the user', () => {
    expect(errorMessage({ message: 'raw object' }, 'Failed.')).toBe('Failed.');
    expect(errorMessage('a string', 'Failed.')).toBe('Failed.');
    expect(errorMessage(undefined, 'Failed.')).toBe('Failed.');
  });

  it('falls back when an Error carries an empty message', () => {
    expect(errorMessage(new Error(''), 'Failed.')).toBe('Failed.');
  });
});
