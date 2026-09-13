import { ReactNode, useEffect, useRef, useId, useState } from 'react';
import FocusTrap from 'focus-trap-react';
import { Alert } from './Alert';
import { LoadingButton } from './Loading';

/**
 * Modal component using DaisyUI classes.
 * Docs: https://daisyui.com/components/modal/
 */
export type ModalPlacement = 'middle' | 'end' | 'start' | 'top' | 'bottom';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'sheet';
  /** Horizontal/vertical dock. `end` is a right-docked sheet (`modal-end`). */
  placement?: ModalPlacement;
  className?: string;
  'aria-label'?: string;
}

export const Modal = ({
  isOpen,
  onClose,
  children,
  title,
  size = 'md',
  placement = 'middle',
  className = '',
  'aria-label': ariaLabel,
}: ModalProps) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const triggerElementRef = useRef<HTMLElement | null>(null);

  // Sync open state with native dialog methods and manage focus
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      if (!dialog.open) {
        triggerElementRef.current = document.activeElement as HTMLElement | null;
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
        if (triggerElementRef.current) {
          triggerElementRef.current.focus();
        }
      }
    }
  }, [isOpen]);

  // Handle native cancel event (e.g. Escape key)
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleCancel = (e: Event) => {
      e.preventDefault(); // Prevent native close to keep React state in sync
      onClose();
    };

    dialog.addEventListener('cancel', handleCancel);
    return () => dialog.removeEventListener('cancel', handleCancel);
  }, [onClose]);

  // Handle backdrop clicks (outside `.modal-box`). The `<dialog class="modal">`
  // is full-viewport, so the dialog rect itself is not a useful hit test —
  // especially for `modal-end` sheets that leave a clickable gutter.
  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    const raw = e.target as Node;
    const el = raw instanceof Element ? raw : raw.parentElement;
    // Form `.modal-backdrop` (or its submit button / text node) has its own handler.
    if (el?.closest('.modal-backdrop')) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const box = dialog.querySelector('.modal-box');
    if (box && !box.contains(raw)) {
      onClose();
    }
  };

  const sizeClasses = {
    sm: 'max-w-sm max-h-[90vh] overflow-y-auto',
    md: 'max-w-md max-h-[90vh] overflow-y-auto',
    lg: 'max-w-lg max-h-[90vh] overflow-y-auto',
    xl: 'max-w-xl max-h-[90vh] overflow-y-auto',
    '2xl': 'max-w-5xl w-11/12 max-h-[90vh] overflow-y-auto',
    sheet: 'h-full max-h-full w-full max-w-4xl rounded-none rounded-s-box overflow-hidden',
  };

  const placementClass = placement === 'middle' ? '' : `modal-${placement}`;

  // Keep FocusTrap mounted and toggle `active` so DaisyUI open/close
  // transitions are not interrupted by remounting the dialog tree.
  return (
    <FocusTrap
      active={isOpen}
      focusTrapOptions={{
        allowOutsideClick: true,
        escapeDeactivates: false,
        fallbackFocus: () => dialogRef.current || document.body,
      }}
    >
      <dialog
        ref={dialogRef}
        className={`modal ${placementClass} ${isOpen ? 'modal-open' : ''}`.replace(/\s+/g, ' ').trim()}
        onClick={handleBackdropClick}
        aria-labelledby={title ? titleId : undefined}
        aria-label={!title ? (ariaLabel || 'Dialog') : undefined}
        aria-modal={isOpen ? true : undefined}
      >
        <div
          className={`modal-box bg-base-100 border border-base-300 shadow-xl ${sizeClasses[size]} ${className}`}
          data-testid="os-overlay-chrome"
          onClick={(e) => e.stopPropagation()}
        >
          {title && (
            <h3 id={titleId} className="font-bold text-lg mb-4">{title}</h3>
          )}
          <div className="modal-content">
            {children}
          </div>
        </div>
        <form
          method="dialog"
          className="modal-backdrop"
          aria-hidden="true"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
        >
          <button
            type="submit"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onClose();
            }}
            aria-label="Close modal"
            tabIndex={-1}
          >
            close
          </button>
        </form>
      </dialog>
    </FocusTrap>
  );
};

/**
 * Confirmation Modal
 */
export interface ConfirmModalProps extends ModalProps {
  onConfirm: () => void | Promise<void>;
  confirmText?: string;
  cancelText?: string;
  confirmVariant?: 'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'error';
}

export const ConfirmModal = ({
  isOpen,
  onClose,
  onConfirm,
  children,
  title = 'Confirm Action',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  confirmVariant = 'primary',
  ...props
}: ConfirmModalProps) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setIsSubmitting(false);
      setError(null);
    }
  }, [isOpen]);

  const handleConfirm = async () => {
    if (isSubmitting) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await onConfirm();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else if (typeof err === 'string') {
        setError(err);
      } else {
        setError('An unknown error occurred');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} {...props}>
      <div className="mb-6">
        {children}
      </div>

      {error && (
        <Alert type="error" className="mb-4">
          {error}
        </Alert>
      )}

      <div className="modal-action flex gap-2">
        <button
          type="button"
          className="btn btn-outline"
          onClick={onClose}
          disabled={isSubmitting}
        >
          {cancelText}
        </button>
        <LoadingButton
          type="button"
          className={`btn btn-${confirmVariant}`}
          onClick={handleConfirm}
          loading={isSubmitting}
        >
          {confirmText}
        </LoadingButton>
      </div>
    </Modal>
  );
};

export default Modal;
