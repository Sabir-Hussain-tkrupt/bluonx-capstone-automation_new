import { useRef, useState } from 'react';
import { FileText, Pencil, Upload } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { API_ENDPOINTS } from '@/constants/api';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { formatDateTime, textareaClass } from '@/features/contingency/components/shared';
import { formatMoney, parseMoneyInput } from '@/features/budgets/utils/money';
import { BENEFICIARY_LABELS, ESCROW_STATUS, FIELD_STEPS, STEP_LABEL } from '../constants';
import { openEscrowDocument, useEscrow, useLongTailWrite, useUploadEscrowDocument } from '../hooks/useLongTail';
import type { EscrowDefect, EscrowDetail } from '../types';
import { EscrowFormModal } from './EscrowFormModal';

type Panel = { kind: 'step'; to: string } | { kind: 'defect'; defect?: EscrowDefect } | { kind: 'renew' } | null;

/** Task 7.3 — lifecycle, defect list, bond renewals and the bond document. */
export function EscrowDetailModal({ escrowId, readOnly = false, onClose }: { escrowId: string; readOnly?: boolean; onClose: () => void }) {
  const query = useEscrow(escrowId);
  const [editing, setEditing] = useState(false);
  const e = query.data;
  if (editing && e) return <EscrowFormModal projectId={e.project_id} escrow={e} onClose={() => setEditing(false)} />;
  return (
    <Modal isOpen onClose={onClose} title={e?.name ?? 'Escrow'} size="lg">
      {query.isLoading ? (
        <Skeleton height="300px" />
      ) : !e ? (
        <Alert variant="danger" title="Could not load the escrow">{errorMessage(query.error, 'Please try again.')}</Alert>
      ) : (
        <Body e={e} readOnly={readOnly} onEdit={() => setEditing(true)} />
      )}
    </Modal>
  );
}

function Body({ e, readOnly, onEdit }: { e: EscrowDetail; readOnly: boolean; onEdit: () => void }) {
  const { toast } = useToast();
  const write = useLongTailWrite();
  const upload = useUploadEscrowDocument(e.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const can = e.permissions;
  const open = !['released', 'cancelled'].includes(e.status);
  const defectsEditable = ['inspection', 'corrections'].includes(e.status) && can.record_works && !readOnly;

  const run = (method: 'post' | 'put', url: string, body: unknown, message: string) =>
    write.mutate({ method, url, body }, {
      onSuccess: () => {
        toast({ variant: 'success', message });
        setPanel(null);
      },
      onError: (err) => toast({ variant: 'danger', message: errorMessage(err, 'Could not save.') }),
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={ESCROW_STATUS[e.status].label} variant={ESCROW_STATUS[e.status].variant} />
        <StatusBadge status={e.security_form === 'bond' ? 'Bond' : 'Cash posted'} variant="neutral" />
        <span className="text-sm text-secondary-600">
          To the {BENEFICIARY_LABELS[e.beneficiary]} for {e.covered_areas.join(', ')}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm md:grid-cols-3">
        <Item label="Value of the works" value={formatMoney(e.secured_amount)} />
        <Item label="Cost 1: premium line" value={formatMoney(e.premium_line_amount)} />
        <Item label="Cost 2: repairs line" value={formatMoney(e.repair_line_amount)} />
        {e.security_form === 'bond' && <Item label="Holder" value={e.holder_name ?? '—'} />}
        {e.security_form === 'bond' && <Item label="Bond expires" value={formatDateOnly(e.bond_expiry_date)} />}
        <Item label="Repair estimate" value={`${formatMoney(e.repair_estimate)}${e.jurisdiction_name ? ` (${e.jurisdiction_name})` : ''}`} />
        <Item label="Posted" value={formatDateOnly(e.posted_date)} />
        <Item label="Inspection walk" value={formatDateOnly(e.inspection_date)} />
        <Item label="Government sign-off" value={e.signoff_date ? `${formatDateOnly(e.signoff_date)} · ${e.signoff_by ?? ''}` : '—'} />
        <Item label={e.released_date ? 'Released' : 'Expected release'} value={formatDateOnly(e.released_date ?? e.expected_release_date)} />
      </dl>
      {e.inspection_notes && <p className="text-sm text-secondary-700">Inspection: {e.inspection_notes}</p>}

      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          {e.next_steps
            .filter((s) => (FIELD_STEPS.has(s) ? can.record_works : can.manage_escrows))
            .filter((s) => s !== 'corrections' || e.open_defects > 0)
            .map((s) => (
              <Button key={s} size="sm" variant={s === 'cancelled' ? 'outline' : 'primary'} onClick={() => setPanel({ kind: 'step', to: s })}>
                {STEP_LABEL[s]}
              </Button>
            ))}
          {open && can.manage_escrows && (
            <Button size="sm" variant="outline" leftIcon={<Pencil className="h-4 w-4" />} onClick={onEdit}>Edit</Button>
          )}
          {open && e.security_form === 'bond' && can.renew_bonds && (
            <Button size="sm" variant="outline" onClick={() => setPanel({ kind: 'renew' })}>Record bond renewal</Button>
          )}
          {can.renew_bonds && (
            <>
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                onChange={(ev) => {
                  const file = ev.target.files?.[0];
                  if (file) upload.mutate(file, {
                    onSuccess: () => toast({ variant: 'success', message: 'Document uploaded.' }),
                    onError: (err) => toast({ variant: 'danger', message: errorMessage(err, 'Could not upload.') }),
                  });
                  ev.target.value = '';
                }}
              />
              <Button size="sm" variant="outline" leftIcon={<Upload className="h-4 w-4" />} isLoading={upload.isPending} onClick={() => fileRef.current?.click()}>
                {e.document_path ? 'Replace document' : 'Upload bond document'}
              </Button>
            </>
          )}
          {e.document_path && (
            <Button size="sm" variant="ghost" leftIcon={<FileText className="h-4 w-4" />} onClick={() => openEscrowDocument(e.id)}>
              {e.document_name ?? 'Document'}
            </Button>
          )}
        </div>
      )}

      {panel?.kind === 'step' && (
        <StepForm to={panel.to} busy={write.isPending} onCancel={() => setPanel(null)}
          onSave={(body) => run('post', API_ENDPOINTS.ESCROW_TRANSITION(e.id), { to: panel.to, ...body }, `${STEP_LABEL[panel.to]}: saved.`)} />
      )}
      {panel?.kind === 'renew' && (
        <RenewForm busy={write.isPending} onCancel={() => setPanel(null)}
          onSave={(body) => run('post', API_ENDPOINTS.ESCROW_RENEW(e.id), body, 'Renewal recorded; the premium line grew by the renewal premium.')} />
      )}
      {panel?.kind === 'defect' && (
        <DefectForm defect={panel.defect} busy={write.isPending} onCancel={() => setPanel(null)}
          onSave={(body) =>
            run(panel.defect ? 'put' : 'post',
              panel.defect ? `${API_ENDPOINTS.ESCROW_DEFECTS(e.id)}/${panel.defect.id}` : API_ENDPOINTS.ESCROW_DEFECTS(e.id),
              body, 'Defect saved. The repairs line follows the defect list.')} />
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-secondary-900">Defect list ({formatMoney(e.defects_total)})</h4>
          {defectsEditable && <Button size="sm" variant="outline" onClick={() => setPanel({ kind: 'defect' })}>Add defect</Button>}
        </div>
        {e.defects.length === 0 ? (
          <p className="text-sm text-secondary-500">No defects recorded.</p>
        ) : (
          <ul className="divide-y divide-secondary-100 rounded-lg border border-secondary-200 text-sm">
            {e.defects.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-secondary-900">{d.description}</div>
                  <div className="text-xs text-secondary-500">{d.location ?? ''} {formatMoney(d.repair_cost)}</div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={d.status} variant={d.status === 'open' ? 'warning' : 'success'} size="sm" />
                  {defectsEditable && <Button size="sm" variant="ghost" onClick={() => setPanel({ kind: 'defect', defect: d })}>Edit</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="mb-2 text-sm font-semibold text-secondary-900">History</h4>
        <ol className="space-y-2 border-l-2 border-secondary-200 pl-4 text-sm">
          {[...e.history].reverse().map((h) => (
            <li key={h.id}>
              <div className="font-medium text-secondary-900">{h.label}</div>
              <div className="text-xs text-secondary-500">{h.actor_name ?? 'System'} · {formatDateTime(h.created_at)}</div>
              {h.note && <div className="text-secondary-700">{h.note}</div>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function StepForm({ to, busy, onSave, onCancel }: { to: string; busy: boolean; onSave: (b: object) => void; onCancel: () => void }) {
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [by, setBy] = useState('');
  const [error, setError] = useState<string>();
  return (
    <div className="space-y-3 rounded-lg border border-secondary-200 p-3">
      <FormField label="Date" htmlFor="st-date"><TextInput id="st-date" type="date" value={on} onChange={(ev) => setOn(ev.target.value)} /></FormField>
      {to === 'signed_off' && (
        <FormField label="Signed off by (government)" htmlFor="st-by" required error={error}>
          <TextInput id="st-by" value={by} onChange={(ev) => setBy(ev.target.value)} placeholder="Name and department" />
        </FormField>
      )}
      <FormField label={to === 'inspection' ? 'Inspection walk results' : 'Note'} htmlFor="st-note">
        <textarea id="st-note" rows={2} value={note} onChange={(ev) => setNote(ev.target.value)} className={textareaClass} />
      </FormField>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Back</Button>
        <Button size="sm" isLoading={busy} onClick={() => {
          if (to === 'signed_off' && !by.trim()) return setError('Who signed off?');
          onSave({ on, note: note.trim() || null, signoff_by: by.trim() || null });
        }}>{STEP_LABEL[to]}</Button>
      </div>
    </div>
  );
}

function RenewForm({ busy, onSave, onCancel }: { busy: boolean; onSave: (b: object) => void; onCancel: () => void }) {
  const [expiry, setExpiry] = useState('');
  const [premium, setPremium] = useState('');
  const [error, setError] = useState<string>();
  return (
    <div className="space-y-3 rounded-lg border border-secondary-200 p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <FormField label="New expiry date" htmlFor="rn-exp" required error={error}>
          <TextInput id="rn-exp" type="date" value={expiry} onChange={(ev) => setExpiry(ev.target.value)} />
        </FormField>
        <FormField label="Renewal premium ($)" htmlFor="rn-prem" required>
          <TextInput id="rn-prem" inputMode="decimal" value={premium} onChange={(ev) => setPremium(ev.target.value)} />
        </FormField>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Back</Button>
        <Button size="sm" isLoading={busy} onClick={() => {
          const p = parseMoneyInput(premium);
          if (!expiry || p == null) return setError('Enter the new expiry and the premium.');
          onSave({ new_expiry_date: expiry, premium: p });
        }}>Save renewal</Button>
      </div>
    </div>
  );
}

function DefectForm({ defect, busy, onSave, onCancel }: { defect?: EscrowDefect; busy: boolean; onSave: (b: object) => void; onCancel: () => void }) {
  const [description, setDescription] = useState(defect?.description ?? '');
  const [location, setLocation] = useState(defect?.location ?? '');
  const [cost, setCost] = useState(defect ? Number(defect.repair_cost).toFixed(2) : '');
  const [status, setStatus] = useState(defect?.status ?? 'open');
  const [error, setError] = useState<string>();
  return (
    <div className="space-y-3 rounded-lg border border-secondary-200 p-3">
      <FormField label="Defect" htmlFor="df-desc" required error={error}>
        <TextInput id="df-desc" value={description} onChange={(ev) => setDescription(ev.target.value)} placeholder="e.g. Cut out and re-pour road section" />
      </FormField>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <FormField label="Location" htmlFor="df-loc"><TextInput id="df-loc" value={location} onChange={(ev) => setLocation(ev.target.value)} /></FormField>
        <FormField label="Repair cost ($)" htmlFor="df-cost"><TextInput id="df-cost" inputMode="decimal" value={cost} onChange={(ev) => setCost(ev.target.value)} /></FormField>
        <FormField label="Status" htmlFor="df-st">
          <Select id="df-st" value={status} onChange={(ev) => setStatus(ev.target.value as EscrowDefect['status'])}
            options={[{ value: 'open', label: 'Open' }, { value: 'repaired', label: 'Repaired' }, { value: 'waived', label: 'Waived by the city' }]} />
        </FormField>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Back</Button>
        <Button size="sm" isLoading={busy} onClick={() => {
          const c = cost.trim() ? parseMoneyInput(cost) : '0';
          if (!description.trim() || c == null) return setError('Describe the defect and enter its cost.');
          onSave({ description: description.trim(), location: location.trim() || null, repair_cost: c, status });
        }}>Save defect</Button>
      </div>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-secondary-500">{label}</dt>
      <dd className="tabular-nums text-secondary-900">{value}</dd>
    </div>
  );
}
