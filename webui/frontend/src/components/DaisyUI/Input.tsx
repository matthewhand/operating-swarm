import { InputHTMLAttributes, forwardRef, useId, ReactNode } from 'react';

/**
 * Input component using DaisyUI 5 classes.
 * Docs: https://daisyui.com/components/input/
 *
 * daisyUI v5 notes: `form-control`, `label-text`, `label-text-alt`, and
 * `input-bordered` were removed. Layout uses utility classes; borders come
 * from the base `input` style. The `bordered` prop is kept for API
 * compatibility and maps to an explicit border for a non-default look.
 */
export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: string;
  bordered?: boolean;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  color?: 'primary' | 'secondary' | 'accent' | 'info' | 'success' | 'warning' | 'error';
  startAdornment?: ReactNode;
  endAdornment?: ReactNode;
  containerClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(({
  label,
  helperText,
  error,
  bordered = true,
  size = 'md',
  color,
  startAdornment,
  endAdornment,
  containerClassName = '',
  className = '',
  id: propId,
  'aria-describedby': propAriaDescribedBy,
  ...props
}, ref) => {
  const generatedId = useId();
  const inputId = propId || generatedId;
  const errorId = error ? `${inputId}-error` : undefined;
  const helperId = helperText ? `${inputId}-helper` : undefined;

  const describedBy = [propAriaDescribedBy, errorId, helperId].filter(Boolean).join(' ') || undefined;

  const baseInputClasses = [
    'input',
    bordered ? '' : 'border-0',
    size === 'xs' ? 'input-xs' :
    size === 'sm' ? 'input-sm' :
    size === 'lg' ? 'input-lg' :
    '',
    color ? `input-${color}` : '',
    error ? 'input-error' : '',
  ].filter(Boolean);

  const hasAdornments = Boolean(startAdornment || endAdornment);

  return (
    <div className={`w-full flex flex-col gap-1 ${containerClassName}`.trim()}>
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium">
          {label}
        </label>
      )}

      {hasAdornments ? (
        <label className={`${baseInputClasses.join(' ')} flex items-center gap-2 ${className}`.trim()}>
          {startAdornment && <span className="shrink-0 flex items-center text-base-content/70">{startAdornment}</span>}
          <input
            id={inputId}
            ref={ref}
            className="grow bg-transparent outline-none border-none p-0 focus:outline-none"
            aria-invalid={!!error}
            aria-describedby={describedBy}
            {...props}
          />
          {endAdornment && <span className="shrink-0 flex items-center text-base-content/70">{endAdornment}</span>}
        </label>
      ) : (
        <input
          id={inputId}
          ref={ref}
          className={`${baseInputClasses.join(' ')} ${className}`.trim()}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          {...props}
        />
      )}

      {error ? (
        <span id={errorId} role="alert" className="text-xs text-error">{error}</span>
      ) : helperText ? (
        <span id={helperId} className="text-xs text-base-content/70">{helperText}</span>
      ) : null}
    </div>
  );
});

Input.displayName = 'Input';

export default Input;
