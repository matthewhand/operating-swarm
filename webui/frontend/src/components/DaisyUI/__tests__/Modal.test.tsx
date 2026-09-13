import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ConfirmModal, Modal } from '../Modal';

describe('Modal Accessibility and Focus Restoration', () => {
  it('captures document.activeElement before opening and restores it on close', async () => {
    render(
      <div>
        <button id="trigger-btn">Open Modal</button>
      </div>
    );
    const triggerBtn = screen.getByRole('button', { name: 'Open Modal' });
    triggerBtn.focus();
    // eslint-disable-next-line testing-library/no-node-access
    expect(document.activeElement).toBe(triggerBtn);

    const onClose = vi.fn();
    const { rerender } = render(
      <div>
        <button id="trigger-btn">Open Modal</button>
        <Modal isOpen={true} onClose={onClose} title="Test Modal">
          <p>Modal content</p>
        </Modal>
      </div>
    );

    expect(screen.getByRole('dialog', { hidden: true })).toBeInTheDocument();

    rerender(
      <div>
        <button id="trigger-btn">Open Modal</button>
        <Modal isOpen={false} onClose={onClose} title="Test Modal">
          <p>Modal content</p>
        </Modal>
      </div>
    );

    await waitFor(() => {
      // eslint-disable-next-line testing-library/no-node-access
      expect(document.activeElement).toBe(triggerBtn);
    });
  });

  it('renders focusable button backdrop and calls onClose when clicked', async () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={onClose} title="Backdrop Test">
        <p>Backdrop content</p>
      </Modal>
    );

    const backdropButton = screen.getByRole('button', { name: 'Close modal', hidden: true });
    expect(backdropButton).toBeInTheDocument();
    expect(backdropButton).toHaveAttribute('tabIndex', '-1');
    // eslint-disable-next-line testing-library/no-node-access
    expect(backdropButton.closest('form')).toHaveAttribute('aria-hidden', 'true');

    backdropButton.click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps FocusTrap mounted and toggles active with isOpen', () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Modal isOpen={false} onClose={onClose} title="Trap Test">
        <button type="button">Inside</button>
      </Modal>
    );

    const dialog = screen.getByRole('dialog', { hidden: true });
    expect(dialog).not.toHaveClass('modal-open');
    expect(dialog).not.toHaveAttribute('aria-modal');

    rerender(
      <Modal isOpen={true} onClose={onClose} title="Trap Test">
        <button type="button">Inside</button>
      </Modal>
    );

    const openDialog = screen.getByRole('dialog', { hidden: true });
    expect(openDialog).toHaveClass('modal-open');
    expect(openDialog).toHaveAttribute('aria-modal', 'true');
  });

  it('applies DaisyUI modal-end for a right-docked sheet', () => {
    render(
      <Modal isOpen={true} onClose={() => {}} placement="end" size="sheet" title="Sheet">
        <p>Docked</p>
      </Modal>
    );
    const dialog = screen.getByRole('dialog', { hidden: true });
    expect(dialog).toHaveClass('modal');
    expect(dialog).toHaveClass('modal-end');
    expect(dialog).not.toHaveClass('drawer');
    // eslint-disable-next-line testing-library/no-node-access
    const box = dialog.querySelector('.modal-box');
    expect(box).toHaveClass('max-w-4xl');
    expect(box).toHaveClass('bg-base-100');
    expect(box).toHaveClass('border');
    expect(box).toHaveClass('shadow-xl');
    expect(box).toHaveClass('overflow-hidden');
  });

  it('closes when the click lands outside modal-box (sheet gutter)', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={onClose} placement="end" size="sheet" title="Sheet">
        <p>Docked</p>
      </Modal>
    );
    const dialog = screen.getByRole('dialog', { hidden: true });
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('exposes aria-label when title is omitted', () => {
    render(
      <Modal isOpen={true} onClose={() => {}} aria-label="Untitled dialog">
        <p>Body</p>
      </Modal>
    );
    expect(screen.getByRole('dialog', { hidden: true })).toHaveAttribute(
      'aria-label',
      'Untitled dialog'
    );
  });
});

describe('ConfirmModal async state', () => {
  it('shows a busy confirm button and ignores a second click while pending', async () => {
    let resolveConfirm: (() => void) | undefined;
    const onConfirm = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveConfirm = resolve;
        }),
    );

    render(
      <ConfirmModal isOpen={true} onClose={() => {}} onConfirm={onConfirm} confirmText="Submit">
        Confirm this action
      </ConfirmModal>,
    );

    const submitBtn = screen.getByRole('button', { name: 'Submit' });
    fireEvent.click(submitBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(submitBtn).toHaveAttribute('aria-busy', 'true');

    fireEvent.click(submitBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);

    resolveConfirm?.();
    await waitFor(() => {
      expect(submitBtn).not.toHaveAttribute('aria-busy', 'true');
    });
  });

  it('surfaces a rejected confirm as a role=alert error', async () => {
    const onConfirm = vi.fn(() => Promise.reject(new Error('Network error')));

    render(
      <ConfirmModal isOpen={true} onClose={() => {}} onConfirm={onConfirm} confirmText="Submit">
        Confirm this action
      </ConfirmModal>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Network error');
  });
});
