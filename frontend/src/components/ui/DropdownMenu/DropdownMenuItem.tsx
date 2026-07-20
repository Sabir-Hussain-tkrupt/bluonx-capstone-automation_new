import { useContext } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';
import { DropdownMenuContext } from './context';

export interface DropdownMenuItemProps {
  icon?: ReactNode;
  /** Red text for delete-style items. */
  destructive?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
}

export function DropdownMenuItem({
  icon,
  destructive = false,
  onClick,
  disabled = false,
  children,
}: DropdownMenuItemProps) {
  const { close } = useContext(DropdownMenuContext);

  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => {
        onClick?.();
        close();
      }}
      className={cn(
        'flex w-full cursor-pointer items-center gap-2 px-4 py-2 text-sm transition-colors',
        'hover:bg-secondary-50 focus-visible:bg-secondary-50 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        destructive
          ? 'text-danger-600 hover:text-danger-700'
          : 'text-secondary-700 hover:text-secondary-900',
      )}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </button>
  );
}
