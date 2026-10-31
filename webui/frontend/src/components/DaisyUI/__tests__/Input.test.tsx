import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Input } from '../Input';

describe('Input Component', () => {
  it('renders input with label and associates label htmlFor with input id', () => {
    render(<Input label="Username" data-testid="username-input" />);
    const label = screen.getByText('Username');
    const input = screen.getByTestId('username-input');

    expect(label).toBeInTheDocument();
    expect(input).toBeInTheDocument();
    expect(label).toHaveAttribute('for', input.getAttribute('id'));
  });

  it('renders error message with alert role and aria-invalid', () => {
    render(
      <Input
        label="Email"
        error="Invalid email address"
        data-testid="email-input"
      />
    );

    const input = screen.getByTestId('email-input');
    expect(input).toHaveAttribute('aria-invalid', 'true');

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Invalid email address');
    expect(input.getAttribute('aria-describedby')).toContain(alert.getAttribute('id'));
  });

  it('renders helperText when error is absent', () => {
    render(
      <Input
        label="Password"
        helperText="Must be at least 8 characters"
        data-testid="pwd-input"
      />
    );

    const input = screen.getByTestId('pwd-input');
    expect(input).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByText('Must be at least 8 characters')).toBeInTheDocument();
  });

  it('merges custom aria-describedby with helper and error ids', () => {
    render(
      <Input
        label="Field"
        aria-describedby="external-hint"
        error="Field required"
        data-testid="field-input"
      />
    );

    const input = screen.getByTestId('field-input');
    const describedBy = input.getAttribute('aria-describedby') || '';
    expect(describedBy).toContain('external-hint');
    expect(describedBy).toContain('-error');
  });

  it('supports size and color classes', () => {
    const { rerender } = render(<Input size="xs" color="primary" data-testid="inp" />);
    expect(screen.getByTestId('inp')).toHaveClass('input-xs', 'input-primary');

    rerender(<Input size="lg" color="secondary" bordered={false} data-testid="inp" />);
    expect(screen.getByTestId('inp')).toHaveClass('input-lg', 'input-secondary', 'border-0');
  });

  it('renders start and end adornments and forwards ref to input element', () => {
    const ref = createRef<HTMLInputElement>();
    render(
      <Input
        ref={ref}
        startAdornment={<span data-testid="start-icon">$</span>}
        endAdornment={<span data-testid="end-icon">USD</span>}
        placeholder="0.00"
      />
    );

    expect(screen.getByTestId('start-icon')).toBeInTheDocument();
    expect(screen.getByTestId('end-icon')).toBeInTheDocument();

    const inputEl = screen.getByPlaceholderText('0.00');
    expect(ref.current).toBe(inputEl);
  });

  it('preserves native event handlers and callbacks', () => {
    const handleChange = vi.fn();
    const handleKeyDown = vi.fn();
    const handleFocus = vi.fn();
    const handleBlur = vi.fn();

    render(
      <Input
        data-testid="events-input"
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
      />
    );

    const input = screen.getByTestId('events-input');

    fireEvent.focus(input);
    expect(handleFocus).toHaveBeenCalledTimes(1);

    fireEvent.change(input, { target: { value: 'test value' } });
    expect(handleChange).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(handleKeyDown).toHaveBeenCalledTimes(1);

    fireEvent.blur(input);
    expect(handleBlur).toHaveBeenCalledTimes(1);
  });
});
