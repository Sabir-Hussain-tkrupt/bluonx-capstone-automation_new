import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { NotificationDropdown } from '../components/NotificationDropdown';
import type { Notification } from '../api/notifications.queries';

const useNotificationsMock = vi.fn();
const markAsReadMutate = vi.fn();
const navigateMock = vi.fn();

vi.mock('@/features/notifications/hooks/useNotifications', () => ({
  useNotifications: () => useNotificationsMock(),
}));

vi.mock('@/features/notifications/hooks/useMarkAsRead', () => ({
  useMarkAsRead: () => ({ mutate: markAsReadMutate, isPending: false }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

function buildNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 'n-1',
    user_id: 'u-1',
    title: 'Insurance expiring in 7 days: ABC Excavation',
    message: 'Vendor insurance expires soon.',
    notification_type: 'insurance_expiring',
    reference_type: 'vendors',
    reference_id: 'vendor-1',
    is_read: false,
    created_at: new Date().toISOString(),
    deep_link_path: '/vendors/vendor-1',
    ...overrides,
  };
}

describe('NotificationDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when there are no notifications', () => {
    useNotificationsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderWithRouter(<NotificationDropdown onClose={vi.fn()} />);
    expect(screen.getByText(/no notifications yet/i)).toBeInTheDocument();
  });

  it('renders notification titles', () => {
    useNotificationsMock.mockReturnValue({
      data: [buildNotification()],
      isLoading: false,
      isError: false,
    });
    renderWithRouter(<NotificationDropdown onClose={vi.fn()} />);
    expect(
      screen.getByText(/Insurance expiring in 7 days: ABC Excavation/i),
    ).toBeInTheDocument();
  });

  it('marks as read and navigates when clicking a deep-linked notification', async () => {
    const onClose = vi.fn();
    useNotificationsMock.mockReturnValue({
      data: [buildNotification()],
      isLoading: false,
      isError: false,
    });
    renderWithRouter(<NotificationDropdown onClose={onClose} />);

    const user = userEvent.setup();
    await user.click(
      screen.getByText(/Insurance expiring in 7 days: ABC Excavation/i),
    );

    expect(markAsReadMutate).toHaveBeenCalledWith('n-1');
    expect(navigateMock).toHaveBeenCalledWith('/vendors/vendor-1');
    expect(onClose).toHaveBeenCalled();
  });

  it('does not call markAsRead for already-read notifications', async () => {
    useNotificationsMock.mockReturnValue({
      data: [buildNotification({ is_read: true })],
      isLoading: false,
      isError: false,
    });
    renderWithRouter(<NotificationDropdown onClose={vi.fn()} />);

    const user = userEvent.setup();
    await user.click(
      screen.getByText(/Insurance expiring in 7 days: ABC Excavation/i),
    );

    expect(markAsReadMutate).not.toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/vendors/vendor-1');
  });

  it('shows "View all" link to /notifications', () => {
    useNotificationsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderWithRouter(<NotificationDropdown onClose={vi.fn()} />);
    const link = screen.getByRole('link', { name: /view all/i });
    expect(link).toHaveAttribute('href', '/notifications');
  });
});
