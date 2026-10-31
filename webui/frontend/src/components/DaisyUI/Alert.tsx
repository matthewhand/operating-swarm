import { forwardRef, HTMLAttributes, ReactNode } from 'react';

/**
 * Alert component using DaisyUI classes
 * Docs: https://daisyui.com/components/alert/
 */
export type AlertType = 'info' | 'success' | 'warning' | 'error';

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  type?: AlertType;
  icon?: ReactNode;
  actions?: ReactNode;
  onClose?: () => void;
  className?: string;
  role?: string;
}

/** Interruptive roles for urgent types; polite status for info/success. */
function defaultRoleForType(type: AlertType): string {
  return type === 'error' || type === 'warning' ? 'alert' : 'status';
}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(({
  children,
  type = 'info',
  icon,
  actions,
  onClose,
  className = '',
  role,
  ...props
}, ref) => {
  const resolvedRole = role ?? defaultRoleForType(type);
  const alertClasses = [
    'alert',
    `alert-${type}`,
    // Keep body text at full opacity on tinted DaisyUI alert surfaces
    // (nested muted utilities can otherwise fail WCAG contrast).
    '[&>:last-child]:text-base-content',
    className
  ].filter(Boolean);

  return (
    <div ref={ref} role={resolvedRole} className={alertClasses.join(' ')} {...props}>
      {icon && <div data-testid="alert-icon-wrapper" className="mr-2 shrink-0" aria-hidden="true">{icon}</div>}
      <div className="min-w-0 flex-1">{children}</div>
      {(actions || onClose) && (
        <div className="flex items-center gap-2 shrink-0">
          {actions}
          {onClose && (
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle"
              onClick={onClose}
              aria-label="Dismiss alert"
            >
              ✕
            </button>
          )}
        </div>
      )}
    </div>
  );
});

Alert.displayName = 'Alert';

/**
 * Success Alert
 */
export const SuccessAlert = forwardRef<HTMLDivElement, Omit<AlertProps, 'type'>>((props, ref) => (
  <Alert ref={ref} type="success" {...props} />
));
SuccessAlert.displayName = 'SuccessAlert';

/**
 * Warning Alert
 */
export const WarningAlert = forwardRef<HTMLDivElement, Omit<AlertProps, 'type'>>((props, ref) => (
  <Alert ref={ref} type="warning" {...props} />
));
WarningAlert.displayName = 'WarningAlert';

/**
 * Error Alert
 */
export const ErrorAlert = forwardRef<HTMLDivElement, Omit<AlertProps, 'type'>>((props, ref) => (
  <Alert ref={ref} type="error" {...props} />
));
ErrorAlert.displayName = 'ErrorAlert';

/**
 * Info Alert (default)
 */
export const InfoAlert = forwardRef<HTMLDivElement, Omit<AlertProps, 'type'>>((props, ref) => (
  <Alert ref={ref} type="info" {...props} />
));
InfoAlert.displayName = 'InfoAlert';

export default Alert;
