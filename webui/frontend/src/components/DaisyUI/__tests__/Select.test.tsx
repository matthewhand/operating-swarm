import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Select, SmartSelect, SelectOption } from '../Select';

describe('Select Component', () => {
  it('renders select with label and associates label htmlFor with select id', () => {
    render(
      <Select label="Role" data-testid="role-select">
        <option value="admin">Admin</option>
        <option value="user">User</option>
      </Select>
    );

    const label = screen.getByText('Role');
    const select = screen.getByTestId('role-select');
    expect(label).toBeInTheDocument();
    expect(select).toBeInTheDocument();
    expect(label).toHaveAttribute('for', select.getAttribute('id'));
  });

  it('renders error message with alert role and aria-invalid', () => {
    render(
      <Select
        label="Role"
        error="Selection is required"
        data-testid="role-select"
      >
        <option value="">Choose</option>
      </Select>
    );

    const select = screen.getByTestId('role-select');
    expect(select).toHaveAttribute('aria-invalid', 'true');

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Selection is required');
    expect(select.getAttribute('aria-describedby')).toContain(alert.getAttribute('id'));
  });

  it('renders helperText when error is absent', () => {
    render(
      <Select
        label="Environment"
        helperText="Choose deployment target"
        data-testid="env-select"
      >
        <option value="prod">Production</option>
      </Select>
    );

    const select = screen.getByTestId('env-select');
    expect(select).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByText('Choose deployment target')).toBeInTheDocument();
  });

  it('merges custom aria-describedby with helper and error ids', () => {
    render(
      <Select
        label="Model"
        aria-describedby="external-help"
        error="Model unavailable"
        data-testid="model-select"
      >
        <option value="gpt">GPT</option>
      </Select>
    );

    const select = screen.getByTestId('model-select');
    const describedBy = select.getAttribute('aria-describedby') || '';
    expect(describedBy).toContain('external-help');
    expect(describedBy).toContain('-error');
  });

  it('supports size and color classes', () => {
    const { rerender } = render(
      <Select size="xs" color="accent" data-testid="s">
        <option value="1">1</option>
      </Select>
    );
    expect(screen.getByTestId('s')).toHaveClass('select-xs', 'select-accent');

    rerender(
      <Select size="lg" color="info" bordered={false} data-testid="s">
        <option value="1">1</option>
      </Select>
    );
    expect(screen.getByTestId('s')).toHaveClass('select-lg', 'select-info', 'border-0');
  });

  it('renders SmartSelect with placeholder and options', () => {
    const options: SelectOption[] = [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'claude-3-5', label: 'Claude 3.5 Sonnet' },
      { value: 'deepseek-r1', label: 'DeepSeek R1', disabled: true },
    ];

    render(
      <SmartSelect
        data-testid="smart-select"
        placeholder="Select model"
        options={options}
      />
    );

    expect(screen.getByText('Select model')).toBeInTheDocument();
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeInTheDocument();

    const disabledOption = screen.getByText('DeepSeek R1');
    expect(disabledOption).toBeDisabled();
  });

  it('renders SmartSelect with optgroups when group is present', () => {
    const options: SelectOption[] = [
      { value: 'auto', label: 'Auto routing' },
      { value: 'claude-3-5', label: 'Claude 3.5', group: 'Anthropic' },
      { value: 'claude-3-haiku', label: 'Claude 3 Haiku', group: 'Anthropic' },
      { value: 'gpt-4o', label: 'GPT-4o', group: 'OpenAI' },
    ];

    const { container } = render(
      <SmartSelect
        data-testid="grouped-select"
        options={options}
      />
    );

    const optgroups = container.querySelectorAll('optgroup');
    expect(optgroups.length).toBe(2);
    expect(optgroups[0]).toHaveAttribute('label', 'Anthropic');
    expect(optgroups[1]).toHaveAttribute('label', 'OpenAI');
  });

  it('forwards ref and fires onChange/onFocus/onBlur', () => {
    const ref = createRef<HTMLSelectElement>();
    const handleChange = vi.fn();
    const handleFocus = vi.fn();
    const handleBlur = vi.fn();

    render(
      <Select
        ref={ref}
        data-testid="interactive-select"
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
      >
        <option value="opt1">Option 1</option>
        <option value="opt2">Option 2</option>
      </Select>
    );

    const select = screen.getByTestId('interactive-select');
    expect(ref.current).toBe(select);

    fireEvent.focus(select);
    expect(handleFocus).toHaveBeenCalledTimes(1);

    fireEvent.change(select, { target: { value: 'opt2' } });
    expect(handleChange).toHaveBeenCalledTimes(1);

    fireEvent.blur(select);
    expect(handleBlur).toHaveBeenCalledTimes(1);
  });
});
