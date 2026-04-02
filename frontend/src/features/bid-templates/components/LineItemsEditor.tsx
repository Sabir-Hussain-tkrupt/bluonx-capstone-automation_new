import { useFieldArray, useFormContext } from 'react-hook-form';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { FormField } from '@/components/ui/FormField';

const ITEM_TYPE_OPTIONS = [
  { value: 'unit_price', label: 'Unit Price' },
  { value: 'lump_sum', label: 'Lump Sum' },
];

export function LineItemsEditor() {
  const {
    register,
    control,
    watch,
    formState: { errors },
  } = useFormContext();

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'items',
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-secondary-900">Line Items</h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            append({
              description: '',
              item_type: 'unit_price',
              unit_of_measure: '',
            })
          }
        >
          + Add Item
        </Button>
      </div>

      {fields.length === 0 && (
        <p className="rounded-lg border border-dashed border-secondary-300 py-8 text-center text-sm text-secondary-500">
          No line items yet. Add items to define the bid structure.
        </p>
      )}

      {fields.map((field, index) => {
        const itemType = watch(`items.${index}.item_type`);
        const itemErrors = (errors.items as Record<string, Record<string, { message?: string }>> | undefined)?.[index];

        return (
          <div
            key={field.id}
            className="grid grid-cols-1 gap-3 rounded-lg border border-secondary-200 bg-secondary-50/50 p-4 sm:grid-cols-12"
          >
            {/* Description — spans more on desktop */}
            <div className="sm:col-span-5">
              <FormField
                label="Description"
                required
                error={itemErrors?.description?.message}
              >
                <TextInput
                  {...register(`items.${index}.description`)}
                  placeholder="e.g. Mobilization, Grading per acre"
                />
              </FormField>
            </div>

            {/* Item Type */}
            <div className="sm:col-span-3">
              <FormField label="Type" required>
                <Select
                  {...register(`items.${index}.item_type`)}
                  options={ITEM_TYPE_OPTIONS}
                />
              </FormField>
            </div>

            {/* Unit of Measure — only for unit_price */}
            <div className="sm:col-span-3">
              {itemType === 'unit_price' ? (
                <FormField
                  label="Unit"
                  required
                  error={itemErrors?.unit_of_measure?.message}
                >
                  <TextInput
                    {...register(`items.${index}.unit_of_measure`)}
                    placeholder="e.g. LF, SY, EA"
                  />
                </FormField>
              ) : (
                <FormField label="Unit">
                  <TextInput disabled placeholder="N/A" />
                </FormField>
              )}
            </div>

            {/* Remove button */}
            <div className="flex items-end sm:col-span-1">
              <button
                type="button"
                onClick={() => remove(index)}
                className="mb-0.5 rounded-lg p-2 text-secondary-400 hover:bg-danger-50 hover:text-danger-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
                aria-label={`Remove item ${index + 1}`}
              >
                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path
                    fillRule="evenodd"
                    d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
