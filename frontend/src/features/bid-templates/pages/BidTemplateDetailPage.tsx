import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidTemplate } from '@/features/bid-templates/hooks/useBidTemplate';
import { BidTemplatePreview } from '@/features/bid-templates/components/BidTemplatePreview';

export function BidTemplateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: template, isLoading } = useBidTemplate(id);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  if (!template) {
    return (
      <div className="py-12 text-center">
        <h2 className="text-lg font-semibold text-secondary-900">Template not found</h2>
        <p className="mt-1 text-sm text-secondary-500">
          The bid template you're looking for doesn't exist or has been deleted.
        </p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/bid-templates')}>
          Back to Templates
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
              {template.name}
            </h1>
            <StatusBadge
              status={template.is_lump_sum ? 'lump_sum' : 'line_items'}
              variant={template.is_lump_sum ? 'info' : 'success'}
              dot={false}
            />
          </div>
          <p className="mt-1 text-sm text-secondary-500">
            Created {new Date(template.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => navigate('/bid-templates')}>
            Back
          </Button>
          <Button onClick={() => navigate(`/bid-templates/${id}/edit`)}>
            Edit Template
          </Button>
        </div>
      </div>

      {/* Template Info */}
      <div className="rounded-lg border border-secondary-200 bg-white p-6">
        <h3 className="mb-4 text-sm font-semibold text-secondary-900">Template Details</h3>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wider text-secondary-500">Trade</dt>
            <dd className="mt-1 text-sm text-secondary-900">
              {template.trade_name || 'General Purpose'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wider text-secondary-500">Bid Format</dt>
            <dd className="mt-1 text-sm text-secondary-900">
              {template.is_lump_sum ? 'Lump Sum' : 'Structured Line Items'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wider text-secondary-500">Line Items</dt>
            <dd className="mt-1 text-sm text-secondary-900">
              {template.is_lump_sum ? 'N/A' : template.items.length}
            </dd>
          </div>
        </dl>
      </div>

      {/* Line Items Table (non-lump-sum only) */}
      {!template.is_lump_sum && template.items.length > 0 && (
        <div className="rounded-lg border border-secondary-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-semibold text-secondary-900">Line Items</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 text-xs font-medium uppercase tracking-wider text-secondary-500">
                  <th className="pb-3 pr-4">#</th>
                  <th className="pb-3 pr-4">Description</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3">Unit of Measure</th>
                </tr>
              </thead>
              <tbody>
                {template.items.map((item, index) => (
                  <tr key={item.id} className="border-b border-secondary-100 last:border-0">
                    <td className="py-3 pr-4 text-secondary-400">{index + 1}</td>
                    <td className="py-3 pr-4 font-medium text-secondary-900">{item.description}</td>
                    <td className="py-3 pr-4 text-secondary-600">
                      {item.item_type === 'unit_price' ? 'Unit Price' : 'Lump Sum'}
                    </td>
                    <td className="py-3 text-secondary-600">
                      {item.item_type === 'unit_price' ? item.unit_of_measure : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Preview */}
      <div className="rounded-lg border border-secondary-200 bg-white p-6">
        <BidTemplatePreview
          isLumpSum={template.is_lump_sum}
          items={template.items.map((item) => ({
            description: item.description,
            item_type: item.item_type,
            unit_of_measure: item.unit_of_measure,
          }))}
        />
      </div>
    </div>
  );
}
