import { useFieldArray, useFormContext } from 'react-hook-form';
import { Trash2 } from 'lucide-react';
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
                <Trash2 className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
