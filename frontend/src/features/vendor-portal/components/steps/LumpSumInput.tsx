import { FormField, TextInput } from '@/components/ui';
import { formatCurrency } from '../../utils/currency';

export interface LumpSumInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  error?: string;
}

export function LumpSumInput({ value, onChange, error }: LumpSumInputProps) {
  return (
    <div className="flex flex-col gap-3">
      <FormField
        label="Total Bid Amount"
        required
        error={error}
        hint="Enter your all-inclusive lump-sum bid in USD."
      >
        <TextInput
          type="number"
          inputMode="decimal"
          min={0}
          step="0.01"
          value={value ?? ''}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(raw === '' ? null : Number(raw));
          }}
          leftAddon={<span>$</span>}
          placeholder="0.00"
          error={!!error}
        />
      </FormField>
      {value !== null && value > 0 && (
        <p className="text-sm text-secondary-600">
          Bid total:{' '}
          <span className="font-semibold text-secondary-900">{formatCurrency(value)}</span>
        </p>
      )}
    </div>
  );
}
