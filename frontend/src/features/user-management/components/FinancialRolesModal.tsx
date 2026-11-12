import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { FINANCIAL_ROLES } from '@/lib/roles';
import { useSetUserRoles } from '../hooks/useUserMutations';
import type { FinancialRole, UserAdminResponse } from '../types';

interface FinancialRolesModalProps {
  user: UserAdminResponse | null;
  onClose: () => void;
}

const FINANCIAL_VALUES = new Set<string>(FINANCIAL_ROLES.map((r) => r.value));

/**
 * Admin: grant / revoke a user's financial roles and mark them as an external
 * or temporary field manager. The base role (Admin / Project Manager) is still
 * changed from the row menu. Revoked roles stay in the audit trail server-side.
 */
export function FinancialRolesModal({ user, onClose }: FinancialRolesModalProps) {
  if (!user) return null;
  return <FinancialRolesForm key={user.id} user={user} onClose={onClose} />;
}

function FinancialRolesForm({ user, onClose }: { user: UserAdminResponse; onClose: () => void }) {
  const { toast } = useToast();
  const setRoles = useSetUserRoles();
  // Initial state straight from the user: this component is mounted per open
  // (keyed by user id), so no effect is needed to sync it.
  const [selected, setSelected] = useState<FinancialRole[]>(() =>
    (user.roles ?? []).filter((r): r is FinancialRole => FINANCIAL_VALUES.has(r)),
  );
  const [external, setExternal] = useState(user.is_employee === false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const toggle = (role: FinancialRole) =>
    setSelected((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]));

  const close = () => {
    if (setRoles.isPending) return;
    onClose();
  };

  const save = () => {
    setSubmitError(null);
    setRoles.mutate(
      { id: user.id, body: { roles: selected, is_employee: !external } },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'Roles updated', message: `${user.full_name}'s financial roles were saved.` });
          onClose();
        },
        onError: (error) => setSubmitError(errorMessage(error, 'Could not update the roles. Please try again.')),
      },
    );
  };

  return (
    <Modal
      isOpen
      onClose={close}
      title="Financial roles"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={setRoles.isPending}>
            Cancel
          </Button>
          <Button onClick={save} isLoading={setRoles.isPending}>
            Save roles
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {submitError && (
          <Alert variant="danger" title="Could not save roles">
            {submitError}
          </Alert>
        )}
        <p className="text-sm text-secondary-600">
          Roles for <strong className="text-secondary-900">{user.full_name}</strong>. A person can hold more
          than one.
        </p>
        <div>
          {FINANCIAL_ROLES.map((r) => (
            <Checkbox
              key={r.value}
              label={r.label}
              description={r.description}
              checked={selected.includes(r.value)}
              onChange={() => toggle(r.value)}
            />
          ))}
          <Checkbox
            label="External / temporary field manager"
            description="Can confirm work in the field but can never authorise payment."
            checked={external}
            onChange={() => setExternal((v) => !v)}
          />
        </div>
      </div>
    </Modal>
  );
}
