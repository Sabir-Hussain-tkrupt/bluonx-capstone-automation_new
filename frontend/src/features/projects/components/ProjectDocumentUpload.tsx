import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { FileUpload } from '@/components/ui/FileUpload';
import { useToast } from '@/components/ui/Toast/useToast';
import { useUploadProjectDocument } from '@/features/projects/hooks/useProjectDocuments';
import {
  PROJECT_DOCUMENT_ACCEPT,
  PROJECT_DOCUMENT_HINT,
  PROJECT_DOCUMENT_MAX_MB,
} from '@/constants/uploads';

interface ProjectDocumentUploadProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ProjectDocumentUpload({ projectId, isOpen, onClose }: ProjectDocumentUploadProps) {
  const { toast } = useToast();
  const uploadMutation = useUploadProjectDocument();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');

  const resetForm = () => {
    setSelectedFile(null);
    setFileError('');
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = () => {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append('file', selectedFile);

    uploadMutation.mutate(
      { projectId, formData },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Document uploaded successfully.' });
          handleClose();
        },
        onError: (error) => {
          const msg = (error as { message?: string })?.message ?? 'Failed to upload document.';
          toast({ variant: 'danger', message: msg });
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Upload Project Document"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={uploadMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            isLoading={uploadMutation.isPending}
            disabled={!selectedFile}
          >
            Upload
          </Button>
        </>
      }
    >
      <div>
        <label className="mb-1 block text-sm font-medium text-secondary-700">
          File <span className="text-danger-500">*</span>
        </label>
        <FileUpload
          accept={PROJECT_DOCUMENT_ACCEPT}
          maxSizeMB={PROJECT_DOCUMENT_MAX_MB}
          onFilesSelected={(files) => {
            setSelectedFile(files[0] ?? null);
            setFileError('');
          }}
          onError={setFileError}
          error={fileError}
          uploading={uploadMutation.isPending}
          hint={PROJECT_DOCUMENT_HINT}
          onRemoveFile={() => setSelectedFile(null)}
        />
      </div>
    </Modal>
  );
}
