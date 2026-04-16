export function PortalFooter() {
  return (
    <footer className="border-t border-secondary-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-4 text-xs text-secondary-500 sm:flex-row sm:px-6">
        <p>
          Powered by <span className="font-semibold text-secondary-700">BluOnX</span>
        </p>
        <p className="text-center sm:text-right">
          Need help? Email{' '}
          <a
            className="text-primary-600 hover:underline"
            href="mailto:bids@bluonx.example"
          >
            bids@bluonx.example
          </a>
        </p>
      </div>
    </footer>
  );
}
