import { TextareaHTMLAttributes, forwardRef, useId, ReactNode } from 'react';

/**
 * Textarea component using DaisyUI classes
 * Docs: https://daisyui.com/components/textarea/
 */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: string;
  bordered?: boolean;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  color?: 'primary' | 'secondary' | 'accent' | 'info' | 'success' | 'warning' | 'error';
  containerClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(({
  label,
  helperText,
  error,
  bordered = true,
  size = 'md',
  color,
  containerClassName = '',
  className = '',
  id: propId,
  'aria-describedby': propAriaDescribedBy,
  ...props
}, ref) => {
  const generatedId = useId();
  const textareaId = propId || generatedId;
  const errorId = error ? `${textareaId}-error` : undefined;
  const helperId = helperText ? `${textareaId}-helper` : undefined;

  const describedBy = [propAriaDescribedBy, errorId, helperId].filter(Boolean).join(' ') || undefined;

  const textareaClasses = [
    'textarea',
    bordered ? '' : 'border-0',
    size === 'xs' ? 'textarea-xs' :
    size === 'sm' ? 'textarea-sm' :
    size === 'lg' ? 'textarea-lg' :
    '',
    color ? `textarea-${color}` : '',
    error ? 'textarea-error' : '',
    className
  ].filter(Boolean);

  return (
    <div className={`w-full flex flex-col gap-1 ${containerClassName}`.trim()}>
      {label && (
        <label htmlFor={textareaId} className="text-sm font-medium">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        ref={ref}
        className={textareaClasses.join(' ')}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />
      {error ? (
        <span id={errorId} role="alert" className="text-xs text-error">{error}</span>
      ) : helperText ? (
        <span id={helperId} className="text-xs text-base-content/70">{helperText}</span>
      ) : null}
    </div>
  );
});

Textarea.displayName = 'Textarea';

export default Textarea;
