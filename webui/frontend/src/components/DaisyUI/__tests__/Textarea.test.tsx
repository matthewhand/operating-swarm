import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Textarea } from '../Textarea';

describe('Textarea Component', () => {
  it('renders textarea with label and associates label htmlFor with textarea id', () => {
    render(<Textarea label="Prompt Description" data-testid="desc-textarea" />);
    const label = screen.getByText('Prompt Description');
    const textarea = screen.getByTestId('desc-textarea');

    expect(label).toBeInTheDocument();
    expect(textarea).toBeInTheDocument();
    expect(label).toHaveAttribute('for', textarea.getAttribute('id'));
  });

  it('renders error message with alert role and aria-invalid', () => {
    render(
      <Textarea
        label="Description"
        error="Description is required"
        data-testid="desc-textarea"
      />
    );

    const textarea = screen.getByTestId('desc-textarea');
    expect(textarea).toHaveAttribute('aria-invalid', 'true');

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Description is required');
    expect(textarea.getAttribute('aria-describedby')).toContain(alert.getAttribute('id'));
  });

  it('renders helperText when error is absent', () => {
    render(
      <Textarea
        label="Bio"
        helperText="Max 500 characters"
        data-testid="bio-textarea"
      />
    );

    const textarea = screen.getByTestId('bio-textarea');
    expect(textarea).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByText('Max 500 characters')).toBeInTheDocument();
  });

  it('merges custom aria-describedby with helper and error ids', () => {
    render(
      <Textarea
        label="Notes"
        aria-describedby="external-desc"
        error="Invalid content"
        data-testid="notes-textarea"
      />
    );

    const textarea = screen.getByTestId('notes-textarea');
    const describedBy = textarea.getAttribute('aria-describedby') || '';
    expect(describedBy).toContain('external-desc');
    expect(describedBy).toContain('-error');
  });

  it('supports size, color, and bordered props', () => {
    const { rerender } = render(<Textarea size="xs" color="primary" data-testid="t" />);
    expect(screen.getByTestId('t')).toHaveClass('textarea-xs', 'textarea-primary');

    rerender(<Textarea size="lg" color="warning" bordered={false} data-testid="t" />);
    expect(screen.getByTestId('t')).toHaveClass('textarea-lg', 'textarea-warning', 'border-0');
  });

  it('forwards ref and preserves standard event handlers', () => {
    const ref = createRef<HTMLTextAreaElement>();
    const handleChange = vi.fn();
    const handleKeyDown = vi.fn();
    const handlePaste = vi.fn();

    render(
      <Textarea
        ref={ref}
        data-testid="ref-textarea"
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        rows={6}
      />
    );

    const textarea = screen.getByTestId('ref-textarea');
    expect(ref.current).toBe(textarea);
    expect(textarea).toHaveAttribute('rows', '6');

    fireEvent.change(textarea, { target: { value: 'Line 1\nLine 2' } });
    expect(handleChange).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    expect(handleKeyDown).toHaveBeenCalledTimes(1);

    fireEvent.paste(textarea, { clipboardData: { getData: () => 'pasted text' } });
    expect(handlePaste).toHaveBeenCalledTimes(1);
  });
});
