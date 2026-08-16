import { useState } from 'react';
import { UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { errorMessage } from '@/lib/api';
import { useContractSigners } from '../hooks/useContractSigners';
import { ContractSignerTable } from '../components/ContractSignerTable';
import { ContractSignerModal } from '../components/ContractSignerModal';
import type { ContractSigner } from '../types';

export function ContractSignersPage() {
  const { data: signers, isLoading, isError, error, refetch } = useContractSigners();
  // null + closed = idle; null + open = add; a row + open = edit.
  const [editing, setEditing] = useState<ContractSigner | null>(null);
  const [isModalOpen, setModalOpen] = useState(false);

  const openAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = (signer: ContractSigner) => {
    setEditing(signer);
    setModalOpen(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-secondary-900">Contract Signers</h1>
            <p className="mt-1 text-sm text-secondary-500">
              Manage the people authorized to sign contracts on behalf of BluOnX. One is
              chosen per award and countersigns before the vendor.
            </p>
          </div>
          <Button
            onClick={openAdd}
            leftIcon={<UserPlus className="h-4 w-4" aria-hidden="true" />}
          >
            Add signer
          </Button>
        </div>
      </div>

      {isError && (
        <Alert
          variant="danger"
          title="Could not load contract signers"
          dismissible
          onDismiss={() => refetch()}
        >
          {errorMessage(error, 'Please try again.')}
        </Alert>
      )}

      <ContractSignerTable
        signers={signers ?? []}
        isLoading={isLoading}
        onEdit={openEdit}
        emptyState={
          <EmptyState
            title="No contract signers yet"
            description="Add someone before awarding a task — every contract needs a BluOnX signer."
          />
        }
      />

      <ContractSignerModal
        isOpen={isModalOpen}
        onClose={() => setModalOpen(false)}
        signer={editing}
      />
    </div>
  );
}
