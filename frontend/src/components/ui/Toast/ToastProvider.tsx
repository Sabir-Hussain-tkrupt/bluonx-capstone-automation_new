import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { Toast } from './Toast';
import type { ToastData } from './Toast';
import { ToastContext } from './ToastContext';

const MAX_TOASTS = 5;

let toastCounter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const dismissAll = useCallback(() => {
    setToasts([]);
  }, []);

  const addToast = useCallback(
    (options: Omit<ToastData, 'id'>) => {
      const id = `toast-${++toastCounter}`;
      const newToast: ToastData = { ...options, id };

      setToasts((prev) => {
        const next = [...prev, newToast];
        if (next.length > MAX_TOASTS) {
          return next.slice(next.length - MAX_TOASTS);
        }
        return next;
      });

      return id;
    },
    [],
  );

  const hasUrgent = toasts.some((t) => t.variant === 'danger');

  return (
    <ToastContext.Provider value={{ toast: addToast, dismiss, dismissAll }}>
      {children}
      {createPortal(
        <div
          aria-live={hasUrgent ? 'assertive' : 'polite'}
          aria-atomic="false"
          className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2"
        >
          {toasts.map((t) => (
            <Toast key={t.id} toast={t} onDismiss={dismiss} />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}
