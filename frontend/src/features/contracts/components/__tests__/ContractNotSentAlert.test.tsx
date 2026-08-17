import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ContractNotSentAlert } from '../ContractNotSentAlert';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/lib/api';
import { makeApiError } from '@/test/api-error';
const mockPost = vi.mocked(api.post);

function render(vendorCompanyName: string | null = 'Acme Grading LLC', onSent = vi.fn()) {
  renderWithRouter(
    <ContractNotSentAlert
      awardId="award-1"
      vendorCompanyName={vendorCompanyName}
      onSent={onSent}
    />,
  );
  return { onSent };
}

/** The Alert's own action, which only opens the confirm dialog. */
async function pressSend(ue: ReturnType<typeof userEvent.setup>) {
  await ue.click(screen.getByRole('button', { name: /send contract/i }));
}

/** The dialog's confirm. Scoped, because both it and the Alert's action carry the
 *  same label once the dialog is open — that repetition is deliberate copy. */
async function confirmSend(ue: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole('dialog');
  await ue.click(within(dialog).getByRole('button', { name: 'Send contract' }));
}

describe('ContractNotSentAlert', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ data: { envelope_id: 'env-1', status: 'sent' } });
  });

  it('names the vendor so the PM knows who is waiting', () => {
    render();
    expect(screen.getByRole('alert')).toHaveTextContent(
      /the contract was not delivered to acme grading llc/i,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/has not received anything/i);
  });

  it('falls back to a generic label when the vendor name is missing', () => {
    render(null);
    expect(screen.getByRole('alert')).toHaveTextContent(/not delivered to the vendor/i);
  });

  it('says "Send contract", never "Resend" — nothing was ever sent', () => {
    render();
    expect(screen.getByRole('button', { name: 'Send contract' })).toBeInTheDocument();
    expect(screen.queryByText(/resend/i)).not.toBeInTheDocument();
  });

  it('does not send until the confirm dialog is accepted', async () => {
    const ue = userEvent.setup();
    render();
    await pressSend(ue);

    // Dialog is up; the real contract has NOT gone anywhere yet.
    expect(await screen.findByText(/only do this if they have not received it/i))
      .toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('POSTs to send-contract with no body once confirmed', async () => {
    const ue = userEvent.setup();
    const { onSent } = render();
    await pressSend(ue);
    await confirmSend(ue);

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/awards/award-1/send-contract'),
    );
    await waitFor(() => expect(onSent).toHaveBeenCalled());
  });

  it('abandons the send when the dialog is cancelled', async () => {
    const ue = userEvent.setup();
    render();
    await pressSend(ue);
    await ue.click(await screen.findByRole('button', { name: 'Cancel' }));

    expect(mockPost).not.toHaveBeenCalled();
  });

  it('renders a server failure inside the Alert, not a vanishing toast', async () => {
    mockPost.mockRejectedValueOnce(
      makeApiError('Awarded submission has no Scope of Work attestation timestamp.', 422),
    );
    const ue = userEvent.setup();
    const { onSent } = render();
    await pressSend(ue);
    await confirmSend(ue);

    const alert = await screen.findByRole('alert');
    await waitFor(() =>
      expect(alert).toHaveTextContent(
        /Awarded submission has no Scope of Work attestation timestamp\./,
      ),
    );
    // Still recoverable: the action stays, and the caller is not told it worked.
    expect(screen.getByRole('button', { name: 'Send contract' })).toBeInTheDocument();
    expect(onSent).not.toHaveBeenCalled();
  });

  it('surfaces the 502 unknown-state error from the duplicate-envelope guard', async () => {
    mockPost.mockRejectedValueOnce(
      makeApiError(
        'Could not confirm with DocuSign whether a contract was already sent for '
          + 'this award. Nothing was sent — please try again shortly.',
        502,
      ),
    );
    const ue = userEvent.setup();
    render();
    await pressSend(ue);
    await confirmSend(ue);

    expect(await screen.findByText(/Nothing was sent/)).toBeInTheDocument();
  });
});
