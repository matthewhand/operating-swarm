import { render, screen, fireEvent } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import {
  useFormValidation,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
  Form,
} from '../FormValidation';

describe('FormValidation Component and Hook', () => {
  it('validates required, minLength, maxLength, and custom rules via useFormValidation', () => {
    const { result } = renderHook(() =>
      useFormValidation(
        { username: '', email: '', count: 0 },
        {
          username: { required: true, minLength: 3 },
          email: { pattern: /^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$/, customMessage: 'Bad email' },
          count: {
            validate: (val) => (val > 0 ? true : 'Count must be positive'),
          },
        }
      )
    );

    expect(result.current.isValid).toBe(false);

    act(() => {
      result.current.validateForm();
    });

    expect(result.current.errors.username).toBe('This field is required');
    expect(result.current.errors.count).toBe('Count must be positive');

    act(() => {
      result.current.handleBlur('username');
    });
    expect(result.current.errors.username).toBe('This field is required');

    act(() => {
      result.current.handleChange('username', 'ab');
    });
    expect(result.current.errors.username).toBe('Minimum 3 characters required');

    act(() => {
      result.current.handleChange('username', 'admin');
      result.current.handleChange('email', 'admin@example.com');
      result.current.handleChange('count', 5);
    });

    act(() => {
      result.current.validateForm();
    });

    expect(result.current.errors.username).toBeUndefined();
    expect(result.current.errors.email).toBeUndefined();
    expect(result.current.errors.count).toBeUndefined();
    expect(result.current.isValid).toBe(true);
  });

  it('renders ValidatedInput with ref and error message when touched', () => {
    const ref = createRef<HTMLInputElement>();
    const onChange = vi.fn();
    const onBlur = vi.fn();

    const { rerender } = render(
      <ValidatedInput
        ref={ref}
        name="testInput"
        label="Test Label"
        value=""
        error="Field error"
        touched={false}
        onChange={onChange}
        onBlur={onBlur}
      />
    );

    const input = screen.getByLabelText('Test Label');
    expect(ref.current).toBe(input);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    rerender(
      <ValidatedInput
        ref={ref}
        name="testInput"
        label="Test Label"
        value=""
        error="Field error"
        touched={true}
        onChange={onChange}
        onBlur={onBlur}
      />
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Field error');

    fireEvent.change(input, { target: { value: 'new' } });
    expect(onChange).toHaveBeenCalledWith('testInput', 'new');

    fireEvent.blur(input);
    expect(onBlur).toHaveBeenCalledWith('testInput');
  });

  it('renders ValidatedSelect and ValidatedTextarea with refs', () => {
    const selectRef = createRef<HTMLSelectElement>();
    const textareaRef = createRef<HTMLTextAreaElement>();

    render(
      <div>
        <ValidatedSelect
          ref={selectRef}
          name="role"
          label="Role"
          value="dev"
          touched={true}
          error="Select valid role"
          options={[{ value: 'dev', label: 'Developer' }]}
          onChange={vi.fn()}
          onBlur={vi.fn()}
        />
        <ValidatedTextarea
          ref={textareaRef}
          name="bio"
          label="Bio"
          value=""
          touched={true}
          error="Bio required"
          onChange={vi.fn()}
          onBlur={vi.fn()}
        />
      </div>
    );

    expect(selectRef.current).toBe(screen.getByLabelText('Role'));
    expect(textareaRef.current).toBe(screen.getByLabelText('Bio'));
    expect(screen.getByText('Select valid role')).toBeInTheDocument();
    expect(screen.getByText('Bio required')).toBeInTheDocument();
  });

  it('renders Form component and submits when valid', async () => {
    const handleSubmit = vi.fn();

    render(
      <Form
        initialValues={{ name: 'Initial' }}
        validationRules={{ name: { required: true } }}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <div>
            <ValidatedInput
              name="name"
              label="Name"
              value={form.values.name}
              error={form.errors.name}
              touched={form.touched.name}
              onChange={(n, v) => form.handleChange(n as 'name', v)}
              onBlur={(n) => form.handleBlur(n as 'name')}
            />
            <button type="submit">Submit Form</button>
          </div>
        )}
      </Form>
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit Form' }));
    });
    expect(handleSubmit).toHaveBeenCalledWith({ name: 'Initial' });
  });
});
