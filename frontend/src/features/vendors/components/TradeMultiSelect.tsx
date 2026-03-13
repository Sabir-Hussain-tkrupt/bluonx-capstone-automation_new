import { useState, useRef, useEffect } from 'react';
import { cn } from '@/utils/cn';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import type { Trade } from '@/features/vendors/api/vendor.queries';

interface TradeMultiSelectProps {
  selectedTradeIds: string[];
  onChange: (tradeIds: string[]) => void;
  label?: string;
  error?: string;
  disabled?: boolean;
}

const phaseLabels: Record<string, string> = {
  due_diligence: 'Due Diligence',
  development: 'Development',
  both: 'Both Phases',
};

export function TradeMultiSelect({
  selectedTradeIds,
  onChange,
  label,
  error,
  disabled = false,
}: TradeMultiSelectProps) {
  const { data: trades = [], isLoading } = useTrades();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedTrades = trades.filter((t) => selectedTradeIds.includes(t.id));

  const toggleTrade = (tradeId: string) => {
    if (selectedTradeIds.includes(tradeId)) {
      onChange(selectedTradeIds.filter((id) => id !== tradeId));
    } else {
      onChange([...selectedTradeIds, tradeId]);
    }
  };

  const removeTrade = (tradeId: string) => {
    onChange(selectedTradeIds.filter((id) => id !== tradeId));
  };

  // Group trades by phase
  const groupedTrades = trades.reduce<Record<string, Trade[]>>((acc, trade) => {
    const phase = trade.phase;
    if (!acc[phase]) acc[phase] = [];
    acc[phase].push(trade);
    return acc;
  }, {});

  return (
    <div ref={containerRef} className="relative w-full">
      {label && (
        <label className="mb-1 block text-sm font-medium text-secondary-700">
          {label}
        </label>
      )}

      {/* Trigger — uses div instead of button to allow nested remove buttons */}
      <div
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        tabIndex={disabled || isLoading ? -1 : 0}
        onClick={() => { if (!disabled && !isLoading) setIsOpen(!isOpen); }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!disabled && !isLoading) setIsOpen(!isOpen); } }}
        className={cn(
          'flex min-h-[40px] w-full cursor-pointer flex-wrap items-center gap-1 rounded-lg border bg-white px-3 py-2 text-left text-sm transition-colors',
          'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
          error ? 'border-danger-500' : 'border-secondary-300',
          (disabled || isLoading) && 'cursor-not-allowed bg-secondary-50 opacity-50',
        )}
      >
        {selectedTrades.length === 0 ? (
          <span className="text-secondary-400">
            {isLoading ? 'Loading trades...' : 'Select trades...'}
          </span>
        ) : (
          selectedTrades.map((trade) => (
            <span
              key={trade.id}
              className="inline-flex items-center gap-1 rounded-md bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700"
            >
              {trade.name}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeTrade(trade.id);
                }}
                className="text-primary-400 hover:text-primary-700"
              >
                <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </button>
            </span>
          ))
        )}
      </div>

      {error && <p className="mt-1 text-sm text-danger-600">{error}</p>}

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-secondary-200 bg-white py-1 shadow-lg">
          {Object.entries(groupedTrades).map(([phase, phaseTrades]) => (
            <div key={phase}>
              <div className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-secondary-400">
                {phaseLabels[phase] ?? phase}
              </div>
              {phaseTrades.map((trade) => {
                const isSelected = selectedTradeIds.includes(trade.id);
                return (
                  <button
                    key={trade.id}
                    type="button"
                    onClick={() => toggleTrade(trade.id)}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-secondary-50',
                      isSelected && 'bg-primary-50',
                    )}
                  >
                    <div
                      className={cn(
                        'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                        isSelected
                          ? 'border-primary-600 bg-primary-600 text-white'
                          : 'border-secondary-300',
                      )}
                    >
                      {isSelected && (
                        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                          <path
                            fillRule="evenodd"
                            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </div>
                    <span className="text-secondary-900">{trade.name}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
