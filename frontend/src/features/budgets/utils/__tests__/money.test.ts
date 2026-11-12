import { describe, expect, it } from 'vitest';
import { formatCents, formatDelta, formatMoney, parseMoneyInput, sumCents, toCents } from '../money';

describe('budget money helpers', () => {
  it('sums in integer cents, so 0.1 + 0.2 is exactly 0.30', () => {
    expect(sumCents([0.1, 0.2])).toBe(30);
    expect(formatCents(sumCents([0.1, 0.2]))).toBe('$0.30');
    expect(sumCents(['400000.10', 1234.2, '22000.03', null])).toBe(42323433);
  });

  it('accepts numbers and strings, treats empty as zero', () => {
    expect(toCents('1234.56')).toBe(123456);
    expect(toCents(1234.56)).toBe(123456);
    expect(toCents(null)).toBe(0);
    expect(toCents('')).toBe(0);
  });

  it('formats with cents and a dash for missing values', () => {
    expect(formatMoney(1500)).toBe('$1,500.00');
    expect(formatMoney('-2000.5')).toBe('-$2,000.50');
    expect(formatMoney(null)).toBe('—');
  });

  it('formats signed differences', () => {
    expect(formatDelta(2000)).toBe('+$2,000.00');
    expect(formatDelta(-500)).toBe('−$500.00');
    expect(formatDelta(0)).toBe('$0.00');
  });

  it('parses typed amounts strictly', () => {
    expect(parseMoneyInput('$1,234.5')).toBe('1234.50');
    expect(parseMoneyInput('10')).toBe('10.00');
    expect(parseMoneyInput('1.005')).toBeNull();
    expect(parseMoneyInput('-5')).toBeNull();
    expect(parseMoneyInput('abc')).toBeNull();
    expect(parseMoneyInput('')).toBeNull();
  });
});
