import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { NotificationBell } from '../components/NotificationBell';

const unreadCountMock = vi.fn();

vi.mock('@/features/notifications/hooks/useUnreadCount', () => ({
  useUnreadCount: () => unreadCountMock(),
}));

// Dropdown opens via state; we don't need its data here.
vi.mock('@/features/notifications/hooks/useNotifications', () => ({
  useNotifications: () => ({ data: [], isLoading: false, isError: false }),
}));

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides the badge when unread count is 0', () => {
    unreadCountMock.mockReturnValue({ data: { count: 0 } });
    renderWithRouter(<NotificationBell />);
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });

  it('shows the unread count when greater than 0', () => {
    unreadCountMock.mockReturnValue({ data: { count: 5 } });
    renderWithRouter(<NotificationBell />);
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('5');
  });

  it('caps the displayed count at 99+', () => {
    unreadCountMock.mockReturnValue({ data: { count: 250 } });
    renderWithRouter(<NotificationBell />);
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('99+');
  });

  it('treats undefined data as zero unread', () => {
    unreadCountMock.mockReturnValue({ data: undefined });
    renderWithRouter(<NotificationBell />);
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });
});
