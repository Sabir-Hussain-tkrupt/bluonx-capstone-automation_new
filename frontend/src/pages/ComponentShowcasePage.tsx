import { useMemo, useState } from 'react';
import {
  Button,
  TextInput,
  Select,
  Checkbox,
  RadioGroup,
  DatePicker,
  FileUpload,
  FormField,
  Card,
  Modal,
  Alert,
  Tabs,
  Accordion,
  Table,
  StatusBadge,
  EmptyState,
  Skeleton,
  SkeletonTable,
} from '@/components/ui';
import type { Column } from '@/components/ui';

// ── Sample data ────────────────────────────────────────────

interface SampleVendor {
  id: string;
  name: string;
  trade: string;
  status: string;
  rating: number;
}

const sampleVendors: SampleVendor[] = [
  { id: '1', name: 'ABC Plumbing', trade: 'Plumbing', status: 'approved', rating: 4.5 },
  { id: '2', name: 'XYZ Electric', trade: 'Electrical', status: 'pending_review', rating: 3.8 },
  { id: '3', name: 'Steel Works Inc', trade: 'Structural Steel', status: 'suspended', rating: 2.1 },
  { id: '4', name: 'Green Landscaping', trade: 'Landscaping', status: 'approved', rating: 4.9 },
  { id: '5', name: 'Concrete Masters', trade: 'Concrete', status: 'active', rating: 4.2 },
];

const vendorColumns: Column<SampleVendor>[] = [
  { id: 'name', header: 'Vendor Name', accessor: 'name', sortable: true },
  { id: 'trade', header: 'Trade', accessor: 'trade', sortable: true },
  {
    id: 'status',
    header: 'Status',
    accessor: (row) => <StatusBadge status={row.status} size="sm" />,
  },
  { id: 'rating', header: 'Rating', accessor: (row) => `${row.rating}/5`, align: 'right', sortable: true },
];

const selectOptions = [
  { value: 'plumbing', label: 'Plumbing' },
  { value: 'electrical', label: 'Electrical' },
  { value: 'hvac', label: 'HVAC' },
  { value: 'concrete', label: 'Concrete' },
];

const radioOptions = [
  { value: 'competitive', label: 'Competitive Bid', description: 'Full bidding process with multiple vendors' },
  { value: 'direct', label: 'Direct Assign', description: 'Assign directly to a specific vendor' },
  { value: 'internal', label: 'Internal', description: 'Budget line item, no vendor involvement' },
];

const tabItems = [
  { id: 'overview', label: 'Overview' },
  { id: 'details', label: 'Details', count: 3 },
  { id: 'history', label: 'History' },
  { id: 'disabled', label: 'Disabled', disabled: true },
];

const accordionItems = [
  { id: '1', title: 'Project Scope', content: 'Detailed project scope information including deliverables, timelines, and milestones.' },
  { id: '2', title: 'Budget Breakdown', content: 'Itemized budget with cost estimates per trade, contingency allocations, and overhead calculations.' },
  { id: '3', title: 'Site Requirements', content: 'Geotechnical survey results, environmental constraints, and utility access points.' },
];

// ── Showcase Component ────────────────────────────────────

export function ComponentShowcasePage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [radioValue, setRadioValue] = useState('competitive');
  const [checkboxChecked, setCheckboxChecked] = useState(false);
  const [sortColumn, setSortColumn] = useState<string | undefined>();
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const [showDismissAlert, setShowDismissAlert] = useState(true);

  const handleSort = (columnId: string) => {
    if (sortColumn === columnId) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(columnId);
      setSortDirection('asc');
    }
  };

  const sortedVendors = useMemo(() => {
    if (!sortColumn) return sampleVendors;
    return [...sampleVendors].sort((a, b) => {
      const aVal = a[sortColumn as keyof SampleVendor];
      const bVal = b[sortColumn as keyof SampleVendor];
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return sortDirection === 'asc' ? cmp : -cmp;
    });
  }, [sortColumn, sortDirection]);

  return (
    <div className="mx-auto max-w-5xl space-y-12 p-8">
      <div>
        <h1 className="text-2xl font-bold text-secondary-900">Component Showcase</h1>
        <p className="mt-1 text-secondary-500">
          BluOnX UI component library — Task 2.5
        </p>
      </div>

      {/* ── Buttons ───────────────────────────────────── */}
      <Section title="Button">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="success">Success</Button>
          <Button variant="warning">Warning</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="outline">Outline</Button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
          <Button isLoading>Loading</Button>
          <Button disabled>Disabled</Button>
          <Button fullWidth variant="outline">Full Width</Button>
        </div>
      </Section>

      {/* ── TextInput ─────────────────────────────────── */}
      <Section title="TextInput">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <TextInput placeholder="Default input" />
          <TextInput placeholder="With error" error="This field is required" />
          <TextInput placeholder="Small" size="sm" />
          <TextInput placeholder="Large" size="lg" />
          <TextInput
            placeholder="With left addon"
            leftAddon={
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
              </svg>
            }
          />
          <TextInput placeholder="Disabled" disabled />
        </div>
      </Section>

      {/* ── Select ────────────────────────────────────── */}
      <Section title="Select">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Select options={selectOptions} placeholder="Choose a trade..." />
          <Select options={selectOptions} error="Please select a trade" placeholder="With error" />
        </div>
      </Section>

      {/* ── Checkbox ──────────────────────────────────── */}
      <Section title="Checkbox">
        <div className="space-y-3">
          <Checkbox
            label="Accept terms and conditions"
            checked={checkboxChecked}
            onChange={(e) => setCheckboxChecked(e.target.checked)}
          />
          <Checkbox
            label="Enable notifications"
            description="Receive email alerts when bid statuses change"
          />
          <Checkbox label="Disabled checkbox" disabled />
        </div>
      </Section>

      {/* ── RadioGroup ────────────────────────────────── */}
      <Section title="RadioGroup">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <RadioGroup
            name="bid-type"
            legend="Bid Type"
            options={radioOptions}
            value={radioValue}
            onChange={setRadioValue}
          />
          <RadioGroup
            name="orientation"
            legend="Horizontal Layout"
            orientation="horizontal"
            options={[
              { value: 'a', label: 'Option A' },
              { value: 'b', label: 'Option B' },
              { value: 'c', label: 'Option C' },
            ]}
          />
        </div>
      </Section>

      {/* ── DatePicker ────────────────────────────────── */}
      <Section title="DatePicker">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <DatePicker />
          <DatePicker error="Date is required" />
          <DatePicker size="lg" />
        </div>
      </Section>

      {/* ── FileUpload ────────────────────────────────── */}
      <Section title="FileUpload">
        <FileUpload
          accept=".pdf,.doc,.docx"
          maxSizeMB={5}
          hint="PDF, DOC up to 5MB"
          onFilesSelected={(files) => console.log('Files:', files)}
          onError={(msg) => console.error('Upload error:', msg)}
        />
      </Section>

      {/* ── FormField ─────────────────────────────────── */}
      <Section title="FormField">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <FormField label="Company Name" required>
            <TextInput placeholder="Enter company name" />
          </FormField>
          <FormField label="Trade Category" hint="Select the primary trade for this vendor">
            <Select options={selectOptions} placeholder="Select trade..." />
          </FormField>
          <FormField label="Email" error="Invalid email address" required>
            <TextInput type="email" placeholder="vendor@example.com" error={true} />
          </FormField>
        </div>
      </Section>

      {/* ── Card ──────────────────────────────────────── */}
      <Section title="Card">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card title="Vendor Summary" subtitle="5 vendors registered">
            <p className="text-sm text-secondary-600">
              Overview of all registered vendors and their current statuses.
            </p>
          </Card>
          <Card
            title="Quick Actions"
            actions={<Button size="sm">Add New</Button>}
          >
            <p className="text-sm text-secondary-600">
              Card with action buttons in the header.
            </p>
          </Card>
        </div>
      </Section>

      {/* ── Modal ─────────────────────────────────────── */}
      <Section title="Modal">
        <Button onClick={() => setModalOpen(true)}>Open Modal</Button>
        <Modal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Confirm Award"
          footer={
            <>
              <Button variant="outline" onClick={() => setModalOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => setModalOpen(false)}>Confirm</Button>
            </>
          }
        >
          <p className="text-sm text-secondary-600">
            Are you sure you want to award this contract to ABC Plumbing?
            This action will notify the vendor and create a contract record.
          </p>
        </Modal>
      </Section>

      {/* ── Alert ─────────────────────────────────────── */}
      <Section title="Alert">
        <div className="space-y-3">
          <Alert variant="success" title="Bid Accepted">
            The vendor has been notified of the award decision.
          </Alert>
          <Alert variant="danger" title="Submission Failed">
            Please check the form for errors and try again.
          </Alert>
          <Alert variant="warning" title="Deadline Approaching">
            Bid submissions close in 2 days.
          </Alert>
          <Alert variant="info" title="New Submissions">
            3 new bid submissions have been received.
          </Alert>
          {showDismissAlert ? (
            <Alert variant="neutral" dismissible onDismiss={() => setShowDismissAlert(false)}>
              This is a dismissible neutral alert. Click X to dismiss.
            </Alert>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setShowDismissAlert(true)}>
              Reset dismissed alert
            </Button>
          )}
        </div>
      </Section>

      {/* ── Tabs ──────────────────────────────────────── */}
      <Section title="Tabs">
        <Tabs tabs={tabItems} activeTab={activeTab} onChange={setActiveTab}>
          <p className="text-sm text-secondary-600">
            Content for the <strong>{activeTab}</strong> tab.
          </p>
        </Tabs>
      </Section>

      {/* ── Accordion ─────────────────────────────────── */}
      <Section title="Accordion">
        <Accordion items={accordionItems} defaultOpen={['1']} />
      </Section>

      {/* ── StatusBadge ───────────────────────────────── */}
      <Section title="StatusBadge">
        <div className="flex flex-wrap gap-3">
          <StatusBadge status="approved" />
          <StatusBadge status="pending_review" />
          <StatusBadge status="suspended" />
          <StatusBadge status="active" />
          <StatusBadge status="draft" />
          <StatusBadge status="submitted" />
          <StatusBadge status="under_review" />
          <StatusBadge status="rejected" />
          <StatusBadge status="completed" />
          <StatusBadge status="overdue" />
          <StatusBadge status="in_progress" />
          <StatusBadge status="awarded" />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <StatusBadge status="approved" size="sm" />
          <StatusBadge status="approved" size="md" />
          <StatusBadge status="approved" size="lg" />
          <StatusBadge status="approved" dot={false} />
        </div>
      </Section>

      {/* ── Skeleton ──────────────────────────────────── */}
      <Section title="Skeleton">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="space-y-3">
            <p className="text-xs font-medium text-secondary-500 uppercase">Text variants</p>
            <Skeleton />
            <Skeleton lines={3} />
          </div>
          <div className="space-y-3">
            <p className="text-xs font-medium text-secondary-500 uppercase">Shape variants</p>
            <div className="flex items-center gap-4">
              <Skeleton variant="circular" width="48px" height="48px" />
              <Skeleton variant="rectangular" width="200px" height="80px" />
            </div>
          </div>
        </div>
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-secondary-500 uppercase">Table skeleton</p>
          <SkeletonTable rows={3} columns={4} />
        </div>
      </Section>

      {/* ── EmptyState ────────────────────────────────── */}
      <Section title="EmptyState">
        <Card>
          <EmptyState
            title="No vendors found"
            description="Get started by adding your first vendor to the system."
            action={<Button>Add Vendor</Button>}
          />
        </Card>
      </Section>

      {/* ── Table ─────────────────────────────────────── */}
      <Section title="Table">
        <Table
          columns={vendorColumns}
          data={sortedVendors}
          keyExtractor={(row) => row.id}
          sortColumn={sortColumn}
          sortDirection={sortDirection}
          onSort={handleSort}
          onRowClick={(row) => console.log('Clicked:', row.name)}
          pagination={{
            page,
            pageSize: 10,
            total: sortedVendors.length,
            onPageChange: setPage,
            onPageSizeChange: (size) => console.log('Page size:', size),
          }}
        />
      </Section>

      {/* ── Table Loading ─────────────────────────────── */}
      <Section title="Table (Loading State)">
        <Table
          columns={vendorColumns}
          data={[]}
          keyExtractor={(row) => row.id}
          isLoading
        />
      </Section>

      {/* ── Table Empty ───────────────────────────────── */}
      <Section title="Table (Empty State)">
        <Table
          columns={vendorColumns}
          data={[]}
          keyExtractor={(row) => row.id}
        />
      </Section>
    </div>
  );
}

// ── Helper ────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold text-secondary-900 border-b border-secondary-200 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}
