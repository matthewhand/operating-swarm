import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Alert, SuccessAlert, WarningAlert, ErrorAlert, InfoAlert } from '../Alert';

describe('Alert Component', () => {
  it('renders default info alert with status role', () => {
    render(<Alert data-testid="alert">System notification</Alert>);
    const el = screen.getByTestId('alert');
    expect(el).toHaveClass('alert', 'alert-info');
    expect(el).toHaveAttribute('role', 'status');
    expect(el).toHaveTextContent('System notification');
  });

  it('assigns alert role for error and warning, and status role for success', () => {
    const { rerender } = render(<Alert type="error" data-testid="a">Error text</Alert>);
    expect(screen.getByTestId('a')).toHaveAttribute('role', 'alert');
    expect(screen.getByTestId('a')).toHaveClass('alert-error');

    rerender(<Alert type="warning" data-testid="a">Warning text</Alert>);
    expect(screen.getByTestId('a')).toHaveAttribute('role', 'alert');
    expect(screen.getByTestId('a')).toHaveClass('alert-warning');

    rerender(<Alert type="success" data-testid="a">Success text</Alert>);
    expect(screen.getByTestId('a')).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('a')).toHaveClass('alert-success');
  });

  it('allows overriding role explicitly', () => {
    render(<Alert type="error" role="region" data-testid="a">Custom role</Alert>);
    expect(screen.getByTestId('a')).toHaveAttribute('role', 'region');
  });

  it('renders icon with aria-hidden', () => {
    render(
      <Alert icon={<span data-testid="icon">🔔</span>}>
        Alert with icon
      </Alert>
    );
    const iconWrapper = screen.getByTestId('alert-icon-wrapper');
    expect(iconWrapper).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders dismiss button and triggers onClose', () => {
    const handleClose = vi.fn();
    render(
      <Alert onClose={handleClose}>
        Dismissible alert
      </Alert>
    );

    const closeBtn = screen.getByRole('button', { name: 'Dismiss alert' });
    expect(closeBtn).toBeInTheDocument();

    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders custom actions alongside close button', () => {
    const handleClose = vi.fn();
    render(
      <Alert
        actions={<button type="button">Retry</button>}
        onClose={handleClose}
      >
        Failed request
      </Alert>
    );

    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dismiss alert' })).toBeInTheDocument();
  });

  it('forwards ref and HTML attributes cleanly', () => {
    const ref = createRef<HTMLDivElement>();
    const handleClick = vi.fn();
    render(
      <Alert
        ref={ref}
        data-testid="ref-alert"
        id="unique-alert"
        aria-live="assertive"
        onClick={handleClick}
      >
        Clickable alert
      </Alert>
    );

    const el = screen.getByTestId('ref-alert');
    expect(ref.current).toBe(el);
    expect(el).toHaveAttribute('id', 'unique-alert');
    expect(el).toHaveAttribute('aria-live', 'assertive');

    fireEvent.click(el);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('renders specialized subcomponents with ref forwarding', () => {
    const sRef = createRef<HTMLDivElement>();
    const wRef = createRef<HTMLDivElement>();
    const eRef = createRef<HTMLDivElement>();
    const iRef = createRef<HTMLDivElement>();

    render(
      <div>
        <SuccessAlert ref={sRef} data-testid="s">Success</SuccessAlert>
        <WarningAlert ref={wRef} data-testid="w">Warning</WarningAlert>
        <ErrorAlert ref={eRef} data-testid="e">Error</ErrorAlert>
        <InfoAlert ref={iRef} data-testid="i">Info</InfoAlert>
      </div>
    );

    expect(screen.getByTestId('s')).toHaveClass('alert-success');
    expect(sRef.current).toBe(screen.getByTestId('s'));

    expect(screen.getByTestId('w')).toHaveClass('alert-warning');
    expect(wRef.current).toBe(screen.getByTestId('w'));

    expect(screen.getByTestId('e')).toHaveClass('alert-error');
    expect(eRef.current).toBe(screen.getByTestId('e'));

    expect(screen.getByTestId('i')).toHaveClass('alert-info');
    expect(iRef.current).toBe(screen.getByTestId('i'));
  });
});
