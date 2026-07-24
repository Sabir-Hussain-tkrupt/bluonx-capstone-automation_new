import { HolidayCalendarPanel } from '../components/HolidayCalendarPanel';

export function HolidayCalendarPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Holiday Calendar</h1>
        <p className="mt-1 max-w-2xl text-sm text-secondary-500">
          Weekends are always excluded from working-day counts; the holidays listed here further
          extend the deadline for vendor response before a milestone check-in is flagged.
        </p>
      </div>

      <HolidayCalendarPanel />
    </div>
  );
}
