import { createContext } from 'react';
import type { ToastData } from './Toast';

export interface ToastContextValue {
  toast: (options: Omit<ToastData, 'id'>) => string;
  dismiss: (id: string) => void;
  dismissAll: () => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
