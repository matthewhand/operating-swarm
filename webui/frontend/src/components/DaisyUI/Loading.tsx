import { forwardRef, HTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * Loading & Skeleton components using DaisyUI classes
 * Docs: https://daisyui.com/components/loading/
 */

export type LoadingType = 'spinner' | 'dots' | 'ring' | 'ball' | 'bars' | 'infinity';
export type LoadingSize = 'xs' | 'sm' | 'md' | 'lg';
export type LoadingColor = 'primary' | 'secondary' | 'accent' | 'neutral' | 'info' | 'success' | 'warning' | 'error' | 'current';

export interface LoadingProps extends HTMLAttributes<HTMLSpanElement> {
  size?: LoadingSize;
  color?: LoadingColor;
  className?: string;
  'aria-label'?: string;
}

const SIZE_CLASSES: Record<LoadingSize, string> = {
  xs: 'loading-xs',
  sm: 'loading-sm',
  md: 'loading-md',
  lg: 'loading-lg',
};

const COLOR_CLASSES: Record<LoadingColor, string> = {
  primary: 'text-primary',
  secondary: 'text-secondary',
  accent: 'text-accent',
  neutral: 'text-neutral',
  info: 'text-info',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-error',
  current: 'text-current',
};

function createLoadingComponent(type: LoadingType, displayName: string) {
  const Component = forwardRef<HTMLSpanElement, LoadingProps>(({
    size = 'md',
    color = 'primary',
    className = '',
    'aria-label': ariaLabel = 'Loading',
    ...props
  }, ref) => {
    const sizeClass = SIZE_CLASSES[size] || 'loading-md';
    const colorClass = COLOR_CLASSES[color] || 'text-primary';

    return (
      <span
        ref={ref}
        className={`loading loading-${type} ${sizeClass} ${colorClass} ${className}`.trim()}
        role="status"
        aria-label={ariaLabel}
        aria-live="polite"
        aria-busy="true"
        {...props}
      />
    );
  });

  Component.displayName = displayName;
  return Component;
}

export const LoadingSpinner = createLoadingComponent('spinner', 'LoadingSpinner');
export const LoadingDots = createLoadingComponent('dots', 'LoadingDots');
export const LoadingRing = createLoadingComponent('ring', 'LoadingRing');
export const LoadingBall = createLoadingComponent('ball', 'LoadingBall');
export const LoadingBars = createLoadingComponent('bars', 'LoadingBars');
export const LoadingInfinity = createLoadingComponent('infinity', 'LoadingInfinity');

export type LoadingSpinnerProps = LoadingProps;

/**
 * Skeleton Loading component
 */
export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string | number;
  height?: string | number;
  className?: string;
  rounded?: boolean;
}

export const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(({
  width = '100%',
  height = '20px',
  className = '',
  rounded = true,
  style,
  ...props
}, ref) => {
  return (
    <div
      ref={ref}
      className={`skeleton ${rounded ? 'rounded' : ''} ${className}`.trim()}
      style={{ width, height, ...style }}
      {...props}
    />
  );
});
Skeleton.displayName = 'Skeleton';

/**
 * Skeleton Text component
 */
export interface SkeletonTextProps extends HTMLAttributes<HTMLDivElement> {
  lines?: number;
  width?: string | number;
  className?: string;
}

export const SkeletonText = forwardRef<HTMLDivElement, SkeletonTextProps>(({
  lines = 3,
  width = '100%',
  className = '',
  ...props
}, ref) => {
  return (
    <div ref={ref} className={`space-y-2 ${className}`.trim()} {...props}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} width={width} height="16px" />
      ))}
    </div>
  );
});
SkeletonText.displayName = 'SkeletonText';

/**
 * Skeleton Card component
 */
export interface SkeletonCardProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export const SkeletonCard = forwardRef<HTMLDivElement, SkeletonCardProps>(({
  className = '',
  ...props
}, ref) => {
  return (
    <div ref={ref} className={`card bg-base-200 ${className}`.trim()} {...props}>
      <div className="card-body">
        <Skeleton width="60%" height="24px" className="mb-4" />
        <SkeletonText lines={3} className="mb-4" />
        <div className="flex gap-2">
          <Skeleton width="80px" height="32px" />
          <Skeleton width="80px" height="32px" />
        </div>
      </div>
    </div>
  );
});
SkeletonCard.displayName = 'SkeletonCard';

/**
 * Skeleton Table component
 */
export interface SkeletonTableProps extends HTMLAttributes<HTMLDivElement> {
  rows?: number;
  columns?: number;
  className?: string;
}

export const SkeletonTable = forwardRef<HTMLDivElement, SkeletonTableProps>(({
  rows = 5,
  columns = 4,
  className = '',
  ...props
}, ref) => {
  return (
    <div ref={ref} className={`overflow-x-auto ${className}`.trim()} {...props}>
      <table className="table w-full">
        <thead>
          <tr>
            {Array.from({ length: columns }).map((_, index) => (
              <th key={index} className="bg-base-300">
                <Skeleton width="80px" height="20px" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex}>
                  <Skeleton width="100%" height="16px" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});
SkeletonTable.displayName = 'SkeletonTable';

/**
 * Loading Overlay component
 */
export interface LoadingOverlayProps extends HTMLAttributes<HTMLDivElement> {
  isLoading?: boolean;
  message?: string;
  className?: string;
}

export const LoadingOverlay = forwardRef<HTMLDivElement, LoadingOverlayProps>(({
  isLoading = true,
  message = 'Loading...',
  className = '',
  ...props
}, ref) => {
  if (!isLoading) return null;

  return (
    <div
      ref={ref}
      className={`fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={message}
      {...props}
    >
      <div className="bg-base-100 p-6 rounded-lg shadow-xl text-center">
        <div className="flex justify-center mb-4" aria-hidden="true">
          <LoadingSpinner size="lg" color="primary" />
        </div>
        <p className="text-lg font-medium">{message}</p>
      </div>
    </div>
  );
});
LoadingOverlay.displayName = 'LoadingOverlay';

/**
 * Button with Loading state
 */
export interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  children?: ReactNode;
}

export const LoadingButton = forwardRef<HTMLButtonElement, LoadingButtonProps>(({
  loading = false,
  children,
  disabled,
  ...props
}, ref) => {
  return (
    <button
      ref={ref}
      {...props}
      disabled={loading || disabled}
      aria-disabled={loading || disabled}
      aria-busy={loading}
    >
      {loading ? (
        <>
          <LoadingSpinner size="sm" color="current" className="mr-2" />
          <span className="sr-only">Loading</span>
          {children}
        </>
      ) : (
        children
      )}
    </button>
  );
});
LoadingButton.displayName = 'LoadingButton';

const LoadingComponents = {
  LoadingSpinner,
  LoadingDots,
  LoadingRing,
  LoadingBall,
  LoadingBars,
  LoadingInfinity,
  Skeleton,
  SkeletonText,
  SkeletonCard,
  SkeletonTable,
  LoadingOverlay,
  LoadingButton,
};

export default LoadingComponents;
