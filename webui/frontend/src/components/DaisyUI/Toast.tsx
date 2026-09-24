import { createContext, useCallback, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';
import {
  NOTIFICATIONS_AUTO_EXPIRE_KEY,
  NOTIFICATIONS_AUTO_EXPIRE_EVENT,
  loadNotificationsAutoExpire,
  saveNotificationsAutoExpire,
} from '../../lib/settingsPrefs';

export {
  NOTIFICATIONS_AUTO_EXPIRE_KEY,
  NOTIFICATIONS_AUTO_EXPIRE_EVENT,
  loadNotificationsAutoExpire,
  saveNotificationsAutoExpire,
};

/**
 * Toast types
 */
export type ToastType = 'success' | 'error' | 'warning' | 'info';

/**
 * Toast categories for classification (#1123)
 */
export type ToastCategory = 'action' | 'info' | 'warning' | 'error' | 'sticky';

/**
 * Default TTLs in milliseconds per toast type (#1123)
 * - Action / success: 4000ms
 * - Info / status: 6000ms
 * - Warning: 8000ms
 * - Error: 12000ms
 */
export const DEFAULT_TOAST_TTLS: Record<ToastType, number> = {
  success: 4000,
  info: 6000,
  warning: 8000,
  error: 12000,
};

/**
 * Default TTLs in milliseconds per toast category (#1123)
 */
export const CATEGORY_DEFAULT_TTLS: Record<ToastCategory, number> = {
  action: 4000,
  info: 6000,
  warning: 8000,
  error: 12000,
  sticky: 0,
};

/** Chat websocket drop / handshake failure / auth-gate outage (REQ-112). */
export const TOAST_KIND_WS_DISCONNECT = 'ws-disconnect';

/**
 * Resolve toast TTL and sticky state (#1123)
 */
export function resolveToastTtl(toast: {
  type?: ToastType;
  ttl?: number | null;
  duration?: number | null;
  sticky?: boolean;
  category?: ToastCategory;
}): { isSticky: boolean; ttl: number } {
  // Sticky opt-in: sticky: true, or duration/ttl is 0 or null, or category is 'sticky'
  if (toast.sticky === true || (toast.category === 'sticky' && toast.sticky !== false)) {
    return { isSticky: true, ttl: 0 };
  }
  if (toast.ttl === 0 || toast.ttl === null || toast.duration === 0 || toast.duration === null) {
    return { isSticky: true, ttl: 0 };
  }

  // Explicit TTL override takes precedence
  if (typeof toast.ttl === 'number' && toast.ttl > 0) {
    return { isSticky: false, ttl: toast.ttl };
  }

  // Duration override takes precedence next
  if (typeof toast.duration === 'number' && toast.duration > 0) {
    return { isSticky: false, ttl: toast.duration };
  }

  // Category default
  if (toast.category && toast.category in CATEGORY_DEFAULT_TTLS) {
    const catTtl = CATEGORY_DEFAULT_TTLS[toast.category];
    if (catTtl === 0) {
      return { isSticky: true, ttl: 0 };
    }
    return { isSticky: false, ttl: catTtl };
  }

  // Type default
  const type = toast.type ?? 'info';
  const defaultTtl = DEFAULT_TOAST_TTLS[type] ?? 6000;
  return { isSticky: false, ttl: defaultTtl };
}

/**
 * Toast interface
 */
export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message: ReactNode;
  duration?: number | null;
  ttl?: number | null;
  sticky?: boolean;
  category?: ToastCategory;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';
  /** When set, addToast replaces any existing toast with the same kind. */
  kind?: string;
}

export interface ToastOptions {
  duration?: number | null;
  ttl?: number | null;
  sticky?: boolean;
  category?: ToastCategory;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';
  kind?: string;
}

/**
 * Toast context
 */
interface ToastContextType {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  dismissByKind: (kind: string) => void;
  success: (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => void;
  error: (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => void;
  warning: (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => void;
  info: (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

/**
 * Toast Provider
 */
export const ToastProvider = ({
  children,
  autoExpire,
}: {
  children: ReactNode;
  autoExpire?: boolean;
}) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Monotonic counter avoids same-millisecond id collisions (duplicate keys).
  const toastIdRef = useRef(0);

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    setToasts(prev => {
      if (toast.kind) {
        const others = prev.filter(existing => existing.kind !== toast.kind);
        const existing = prev.find(candidate => candidate.kind === toast.kind);
        if (existing) {
          return [...others, { ...existing, ...toast }];
        }
      }
      toastIdRef.current += 1;
      const id = `toast-${Date.now()}-${toastIdRef.current}`;
      return [...prev, { ...toast, id }];
    });
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  const dismissByKind = useCallback((kind: string) => {
    setToasts(prev => prev.filter(toast => toast.kind !== kind));
  }, []);

  const parseOptions = (durationOrOptions?: number | ToastOptions): ToastOptions => {
    if (typeof durationOrOptions === 'number') {
      return { duration: durationOrOptions };
    }
    return durationOrOptions ?? {};
  };

  const success = useCallback(
    (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => {
      const opts = parseOptions(durationOrOptions);
      addToast({ type: 'success', title, message, position: 'top-right', ...opts });
    },
    [addToast],
  );

  const error = useCallback(
    (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => {
      const opts = parseOptions(durationOrOptions);
      addToast({ type: 'error', title, message, position: 'top-right', ...opts });
    },
    [addToast],
  );

  const warning = useCallback(
    (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => {
      const opts = parseOptions(durationOrOptions);
      addToast({ type: 'warning', title, message, position: 'top-right', ...opts });
    },
    [addToast],
  );

  const info = useCallback(
    (title: string, message: ReactNode, durationOrOptions?: number | ToastOptions) => {
      const opts = parseOptions(durationOrOptions);
      addToast({ type: 'info', title, message, position: 'top-right', ...opts });
    },
    [addToast],
  );

  return (
    <ToastContext.Provider
      value={{ toasts, addToast, removeToast, dismissByKind, success, error, warning, info }}
    >
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} autoExpire={autoExpire} />
    </ToastContext.Provider>
  );
};

/**
 * Toast Container - renders all toasts
 */
export interface ToastContainerProps {
  toasts: Toast[];
  removeToast: (id: string) => void;
  autoExpire?: boolean;
}

export const ToastContainer = ({
  toasts,
  removeToast,
  autoExpire: autoExpireProp,
}: ToastContainerProps) => {
  const [autoExpireState, setAutoExpireState] = useState<boolean>(() =>
    loadNotificationsAutoExpire(),
  );

  useEffect(() => {
    const handleExpireEvent = (e: Event) => {
      const detail = (e as CustomEvent<{ enabled: boolean }>).detail;
      if (detail && typeof detail.enabled === 'boolean') {
        setAutoExpireState(detail.enabled);
      } else {
        setAutoExpireState(loadNotificationsAutoExpire());
      }
    };
    const handleStorageEvent = (e: StorageEvent) => {
      if (e.key === NOTIFICATIONS_AUTO_EXPIRE_KEY) {
        setAutoExpireState(loadNotificationsAutoExpire());
      }
    };

    window.addEventListener(NOTIFICATIONS_AUTO_EXPIRE_EVENT, handleExpireEvent);
    window.addEventListener('storage', handleStorageEvent);
    return () => {
      window.removeEventListener(NOTIFICATIONS_AUTO_EXPIRE_EVENT, handleExpireEvent);
      window.removeEventListener('storage', handleStorageEvent);
    };
  }, []);

  const autoExpire = autoExpireProp ?? autoExpireState;

  // Group toasts by position
  const groupedToasts = toasts.reduce(
    (acc, toast) => {
      const position = toast.position || 'top-right';
      if (!acc[position]) {
        acc[position] = [];
      }
      acc[position].push(toast);
      return acc;
    },
    {} as Record<string, Toast[]>,
  );

  return (
    <>
      {Object.entries(groupedToasts).map(([position, positionToasts]) => (
        <div key={position} className={`fixed ${getPositionClasses(position)} z-50 space-y-2`}>
          {positionToasts.map(toast => (
            <ToastItem
              key={toast.id}
              toast={toast}
              removeToast={removeToast}
              autoExpireEnabled={autoExpire}
            />
          ))}
        </div>
      ))}
    </>
  );
};

/**
 * Get position classes for toast container
 */
const getPositionClasses = (position: string) => {
  switch (position) {
    case 'top-right':
      return 'top-20 right-4';
    case 'top-left':
      return 'top-20 left-4';
    case 'bottom-right':
      return 'bottom-4 right-4';
    case 'bottom-left':
      return 'bottom-4 left-4';
    default:
      return 'top-4 right-4';
  }
};

/**
 * Individual Toast Item
 */
export interface ToastItemProps {
  toast: Toast;
  removeToast: (id: string) => void;
  autoExpireEnabled?: boolean;
}

export const ToastItem = ({
  toast,
  removeToast,
  autoExpireEnabled = true,
}: ToastItemProps) => {
  const { isSticky: toastIsSticky, ttl } = resolveToastTtl(toast);
  // When auto-expiry is disabled, every toast behaves as sticky.
  const isSticky = toastIsSticky || !autoExpireEnabled;

  const [isHovered, setIsHovered] = useState(false);
  const remainingRef = useRef<number>(ttl);
  const startTimeRef = useRef<number>(Date.now());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // If toast content is updated (e.g. kind-deduplicated update), reset the timer.
  const lastContentRef = useRef({ title: toast.title, message: toast.message });
  useEffect(() => {
    if (
      lastContentRef.current.title !== toast.title ||
      lastContentRef.current.message !== toast.message
    ) {
      lastContentRef.current = { title: toast.title, message: toast.message };
      remainingRef.current = ttl;
      startTimeRef.current = Date.now();
    }
  }, [toast.title, toast.message, ttl]);

  useEffect(() => {
    // If sticky or ttl <= 0, do not set an expiry timer.
    if (isSticky || ttl <= 0) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    // While hovered, pause the expiry timer.
    if (isHovered) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    // If remaining time is already exhausted, remove immediately.
    if (remainingRef.current <= 0) {
      removeToast(toast.id);
      return;
    }

    startTimeRef.current = Date.now();
    timerRef.current = setTimeout(() => {
      removeToast(toast.id);
    }, remainingRef.current);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isHovered, isSticky, ttl, toast.id, removeToast]);

  const handleMouseEnter = () => {
    if (isSticky || ttl <= 0) return;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const elapsed = Date.now() - startTimeRef.current;
    remainingRef.current = Math.max(0, remainingRef.current - elapsed);
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    if (isSticky || ttl <= 0) return;
    if (remainingRef.current <= 0) {
      removeToast(toast.id);
      return;
    }
    setIsHovered(false);
  };

  // Get toast colors and icons
  const { icon: Icon, bgColor, textColor } = getToastStyle(toast.type);

  const live = toast.type === 'error' || toast.type === 'warning' ? 'assertive' : 'polite';

  return (
    <div
      className={`alert ${bgColor} ${textColor} shadow-lg max-w-sm w-full`}
      role="status"
      aria-live={live}
      aria-atomic="true"
      data-toast-kind={toast.kind}
      data-toast-type={toast.type}
      data-toast-category={toast.category}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="flex items-start gap-3">
        <div className="mt-1">
          <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <h3 className="font-bold">{toast.title}</h3>
          <div className="text-sm mt-1">{toast.message}</div>
        </div>
      </div>
      <button
        type="button"
        className="btn btn-sm btn-ghost btn-circle ml-2"
        onClick={() => removeToast(toast.id)}
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
};

/**
 * Get toast style based on type
 */
const getToastStyle = (type: ToastType) => {
  switch (type) {
    case 'success':
      return {
        icon: CheckCircle2,
        bgColor: 'bg-success text-success-content',
        textColor: 'text-success-content',
      };
    case 'error':
      return {
        icon: AlertCircle,
        bgColor: 'bg-error text-error-content',
        textColor: 'text-error-content',
      };
    case 'warning':
      return {
        icon: AlertTriangle,
        bgColor: 'bg-warning text-warning-content',
        textColor: 'text-warning-content',
      };
    case 'info':
      return {
        icon: Info,
        bgColor: 'bg-info text-info-content',
        textColor: 'text-info-content',
      };
    default:
      return {
        icon: Info,
        bgColor: 'bg-info text-info-content',
        textColor: 'text-info-content',
      };
  }
};

/**
 * Custom hook for using toast
 */
export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

/** Toast when a provider is present; null in isolated rail tests. */
export const useOptionalToast = () => useContext(ToastContext);

/**
 * Convenience hooks for specific toast types
 */
export const useSuccessToast = () => {
  const { success } = useToast();
  return success;
};

export const useErrorToast = () => {
  const { error } = useToast();
  return error;
};

export const useWarningToast = () => {
  const { warning } = useToast();
  return warning;
};

export const useInfoToast = () => {
  const { info } = useToast();
  return info;
};

const ToastComponents = {
  ToastProvider,
  ToastContainer,
  ToastItem,
  useToast,
  useOptionalToast,
  useSuccessToast,
  useErrorToast,
  useWarningToast,
  useInfoToast,
  DEFAULT_TOAST_TTLS,
  CATEGORY_DEFAULT_TTLS,
  resolveToastTtl,
};

export default ToastComponents;
