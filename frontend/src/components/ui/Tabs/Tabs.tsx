import { useCallback, useRef } from 'react';
import { cn } from '@/utils/cn';
import type { ComponentSize } from '../types';

export interface Tab {
  id: string;
  label: string;
  disabled?: boolean;
  count?: number;
}

export interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  size?: ComponentSize;
  children: React.ReactNode;
}

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

export function Tabs({
  tabs,
  activeTab,
  onChange,
  size = 'md',
  children,
}: TabsProps) {
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const enabledTabs = tabs.filter((t) => !t.disabled);
      const currentIndex = enabledTabs.findIndex((t) => t.id === activeTab);
      let nextIndex = currentIndex;

      if (e.key === 'ArrowRight') {
        nextIndex = (currentIndex + 1) % enabledTabs.length;
      } else if (e.key === 'ArrowLeft') {
        nextIndex = (currentIndex - 1 + enabledTabs.length) % enabledTabs.length;
      } else if (e.key === 'Home') {
        nextIndex = 0;
      } else if (e.key === 'End') {
        nextIndex = enabledTabs.length - 1;
      } else {
        return;
      }

      e.preventDefault();
      const nextTab = enabledTabs[nextIndex];
      onChange(nextTab.id);
      tabRefs.current.get(nextTab.id)?.focus();
    },
    [tabs, activeTab, onChange],
  );

  return (
    <div>
      <div
        role="tablist"
        className="flex overflow-x-auto border-b border-secondary-200 scrollbar-hide"
        onKeyDown={handleKeyDown}
      >
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                if (el) tabRefs.current.set(tab.id, el);
              }}
              role="tab"
              type="button"
              id={`tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              disabled={tab.disabled}
              onClick={() => onChange(tab.id)}
              className={cn(
                'relative shrink-0 font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none',
                sizeStyles[size],
                isActive
                  ? 'text-primary-600'
                  : 'text-secondary-500 hover:text-secondary-700',
                tab.disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              <span className="flex items-center gap-2">
                {tab.label}
                {tab.count !== undefined && (
                  <span
                    className={cn(
                      'inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium',
                      isActive
                        ? 'bg-primary-100 text-primary-700'
                        : 'bg-secondary-100 text-secondary-600',
                    )}
                  >
                    {tab.count}
                  </span>
                )}
              </span>
              {/* Active underline */}
              {isActive && (
                <span className="absolute inset-x-0 -bottom-px h-0.5 bg-primary-600" />
              )}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
        tabIndex={0}
        className="py-4"
      >
        {children}
      </div>
    </div>
  );
}
