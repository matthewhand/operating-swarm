import { forwardRef, HTMLAttributes, ReactNode } from 'react';

/**
 * Badge component using DaisyUI 5 classes
 * Docs: https://daisyui.com/components/badge/
 */
export type BadgeColor = 'neutral' | 'primary' | 'secondary' | 'accent' | 'ghost' | 'info' | 'success' | 'warning' | 'error';
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  children?: ReactNode;
  /** Primary color variant; `color` or `type` are accepted */
  type?: BadgeColor;
  color?: BadgeColor;
  size?: BadgeSize;
  outline?: boolean;
  className?: string;
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(({
  children,
  type,
  color,
  size = 'md',
  outline = false,
  className = '',
  ...props
}, ref) => {
  const resolvedColor = color ?? type ?? 'neutral';

  const badgeClasses = [
    'badge',
    outline ? 'badge-outline' : `badge-${resolvedColor}`,
    size === 'xs' ? 'badge-xs' :
    size === 'sm' ? 'badge-sm' :
    size === 'lg' ? 'badge-lg' :
    '',
    className
  ].filter(Boolean);

  return (
    <span ref={ref} className={badgeClasses.join(' ')} {...props}>
      {children}
    </span>
  );
});

Badge.displayName = 'Badge';

/**
 * Specialized Badge helpers with ref forwarding
 */
export const PrimaryBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="primary" {...props} />
));
PrimaryBadge.displayName = 'PrimaryBadge';

export const SuccessBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="success" {...props} />
));
SuccessBadge.displayName = 'SuccessBadge';

export const WarningBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="warning" {...props} />
));
WarningBadge.displayName = 'WarningBadge';

export const ErrorBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="error" {...props} />
));
ErrorBadge.displayName = 'ErrorBadge';

export const InfoBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="info" {...props} />
));
InfoBadge.displayName = 'InfoBadge';

export const NeutralBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="neutral" {...props} />
));
NeutralBadge.displayName = 'NeutralBadge';

export const GhostBadge = forwardRef<HTMLSpanElement, Omit<BadgeProps, 'color' | 'type'>>((props, ref) => (
  <Badge ref={ref} color="ghost" {...props} />
));
GhostBadge.displayName = 'GhostBadge';

export default Badge;
