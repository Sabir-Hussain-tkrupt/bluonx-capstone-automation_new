import type { ReactNode } from 'react';
import { Alert } from '@/components/ui';

export interface PortalErrorPageProps {
  icon: ReactNode;
  title: string;
  message: string;
  variant?: 'danger' | 'warning' | 'info';
  helpText?: ReactNode;
}

export function PortalErrorPage({
  icon,
  title,
  message,
  variant = 'warning',
  helpText,
}: PortalErrorPageProps) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-12 text-center sm:py-16">
      <div
        aria-hidden="true"
        className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary-100 text-secondary-600"
      >
        {icon}
      </div>
      <h1 className="mt-4 text-2xl font-bold text-secondary-900 sm:text-3xl">{title}</h1>
      <p className="mt-2 max-w-md text-sm text-secondary-600">{message}</p>

      <div className="mt-6 w-full text-left">
        <Alert variant={variant} title="Need help?">
          {helpText ?? (
            <>
              If you believe this is a mistake, please contact the BluOnX project manager
              that sent you the invitation, or email{' '}
              <a className="font-semibold underline" href="mailto:bids@bluonx.example">
                bids@bluonx.example
              </a>
              .
            </>
          )}
        </Alert>
      </div>
    </div>
  );
}
