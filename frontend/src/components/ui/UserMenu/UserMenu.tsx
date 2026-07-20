import { ChevronDown, LogOut } from 'lucide-react';
import { DropdownMenu, DropdownMenuItem } from '../DropdownMenu';
import { getInitials } from './getInitials';

export interface UserMenuItem {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
}

export interface UserMenuProps {
  userName: string;
  userEmail: string;
  userRole: string;
  avatarUrl?: string;
  menuItems?: UserMenuItem[];
  onSignOut: () => void;
}

export function UserMenu({
  userName,
  userEmail,
  userRole,
  avatarUrl,
  menuItems = [],
  onSignOut,
}: UserMenuProps) {
  const trigger = (
    <button
      type="button"
      className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-secondary-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
    >
      {avatarUrl ? (
        <img
          src={avatarUrl}
          alt={userName}
          className="h-8 w-8 rounded-full object-cover"
        />
      ) : (
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-xs font-semibold text-primary-700">
          {getInitials(userName)}
        </span>
      )}
      <span className="hidden text-left md:block">
        <span className="block text-sm font-medium text-secondary-900">{userName}</span>
        <span className="block text-xs text-secondary-500">{userRole}</span>
      </span>
      <ChevronDown className="hidden h-4 w-4 text-secondary-400 md:block" aria-hidden="true" />
    </button>
  );

  return (
    <DropdownMenu trigger={trigger} align="right" side="bottom" className="w-56">
      <div className="border-b border-secondary-100 px-4 py-3">
        <p className="text-sm font-medium text-secondary-900">{userName}</p>
        <p className="text-xs text-secondary-500">{userEmail}</p>
      </div>

      {menuItems.map((item) => (
        <DropdownMenuItem key={item.label} icon={item.icon} onClick={item.onClick}>
          {item.label}
        </DropdownMenuItem>
      ))}

      {menuItems.length > 0 && <div className="my-1 border-t border-secondary-100" />}

      <DropdownMenuItem
        destructive
        icon={<LogOut className="h-4 w-4" aria-hidden="true" />}
        onClick={onSignOut}
      >
        Sign out
      </DropdownMenuItem>
    </DropdownMenu>
  );
}
