import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { InsuranceExpiringBadge } from '../InsuranceExpiringBadge';

const useHookMock = vi.fn();

vi.mock('@/features/vendors/hooks/useInsuranceExpiringCount', () => ({
  useInsuranceExpiringCount: () => useHookMock(),
}));

describe('InsuranceExpiringBadge', () => {
  it('renders the count and label when > 0', () => {
    useHookMock.mockReturnValue({ data: { count: 4 }, isLoading: false, isError: false });
    renderWithRouter(<InsuranceExpiringBadge />);
    expect(screen.getByTestId('insurance-expiring-badge')).toHaveTextContent('4 insurance alerts');
  });

  it('uses singular "alert" when count is exactly 1', () => {
    useHookMock.mockReturnValue({ data: { count: 1 }, isLoading: false, isError: false });
    renderWithRouter(<InsuranceExpiringBadge />);
    expect(screen.getByTestId('insurance-expiring-badge')).toHaveTextContent('1 insurance alert');
  });

  it('is hidden when count is 0', () => {
    useHookMock.mockReturnValue({ data: { count: 0 }, isLoading: false, isError: false });
    renderWithRouter(<InsuranceExpiringBadge />);
    expect(screen.queryByTestId('insurance-expiring-badge')).not.toBeInTheDocument();
  });

  it('is hidden while loading', () => {
    useHookMock.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderWithRouter(<InsuranceExpiringBadge />);
    expect(screen.queryByTestId('insurance-expiring-badge')).not.toBeInTheDocument();
  });

  it('is hidden on error', () => {
    useHookMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderWithRouter(<InsuranceExpiringBadge />);
    expect(screen.queryByTestId('insurance-expiring-badge')).not.toBeInTheDocument();
  });

  it('uses the warning Tailwind classes', () => {
    useHookMock.mockReturnValue({ data: { count: 2 }, isLoading: false, isError: false });
    renderWithRouter(<InsuranceExpiringBadge />);
    const badge = screen.getByTestId('insurance-expiring-badge');
    expect(badge.className).toContain('bg-warning-100');
    expect(badge.className).toContain('text-warning-700');
  });
});
