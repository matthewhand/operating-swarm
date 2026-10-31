import { SelectHTMLAttributes, forwardRef, ReactNode, useId } from 'react';

/**
 * Select component using DaisyUI classes
 * Docs: https://daisyui.com/components/select/
 */
export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: string;
  bordered?: boolean;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  color?: 'primary' | 'secondary' | 'accent' | 'info' | 'success' | 'warning' | 'error';
  containerClassName?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(({
  label,
  helperText,
  error,
  bordered = true,
  size = 'md',
  color,
  children,
  containerClassName = '',
  className = '',
  id: propId,
  'aria-describedby': propAriaDescribedBy,
  ...props
}, ref) => {
  const generatedId = useId();
  const selectId = propId || generatedId;
  const errorId = error ? `${selectId}-error` : undefined;
  const helperId = helperText ? `${selectId}-helper` : undefined;

  const describedBy = [propAriaDescribedBy, errorId, helperId].filter(Boolean).join(' ') || undefined;

  const selectClasses = [
    'select',
    bordered ? '' : 'border-0',
    size === 'xs' ? 'select-xs' :
    size === 'sm' ? 'select-sm' :
    size === 'lg' ? 'select-lg' :
    '',
    color ? `select-${color}` : '',
    error ? 'select-error' : '',
    className
  ].filter(Boolean);

  return (
    <div className={`w-full flex flex-col gap-1 ${containerClassName}`.trim()}>
      {label && (
        <label htmlFor={selectId} className="text-sm font-medium">
          {label}
        </label>
      )}
      <select
        id={selectId}
        ref={ref}
        className={selectClasses.join(' ')}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      >
        {children}
      </select>
      {error ? (
        <span id={errorId} role="alert" className="text-xs text-error">{error}</span>
      ) : helperText ? (
        <span id={helperId} className="text-xs text-base-content/70">{helperText}</span>
      ) : null}
    </div>
  );
});

Select.displayName = 'Select';

/**
 * Select with custom options
 */
export interface SelectOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
  group?: string;
}

export interface SmartSelectProps extends Omit<SelectProps, 'children'> {
  options: SelectOption[];
  placeholder?: string;
}

export const SmartSelect = forwardRef<HTMLSelectElement, SmartSelectProps>(({
  options,
  placeholder = 'Select an option',
  ...props
}, ref) => {
  const hasGroups = options.some((opt) => Boolean(opt.group));

  let renderedOptions: ReactNode;
  if (!hasGroups) {
    renderedOptions = options.map((option) => (
      <option key={option.value} value={option.value} disabled={option.disabled}>
        {option.label}
      </option>
    ));
  } else {
    const groups = new Map<string, SelectOption[]>();
    const ungrouped: SelectOption[] = [];

    for (const opt of options) {
      if (opt.group) {
        const list = groups.get(opt.group) || [];
        list.push(opt);
        groups.set(opt.group, list);
      } else {
        ungrouped.push(opt);
      }
    }

    renderedOptions = (
      <>
        {ungrouped.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
        {Array.from(groups.entries()).map(([groupName, groupOptions]) => (
          <optgroup key={groupName} label={groupName}>
            {groupOptions.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </optgroup>
        ))}
      </>
    );
  }

  return (
    <Select ref={ref} {...props}>
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {renderedOptions}
    </Select>
  );
});

SmartSelect.displayName = 'SmartSelect';

export default Select;
