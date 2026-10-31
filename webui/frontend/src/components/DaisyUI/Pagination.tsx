import { useState, forwardRef, HTMLAttributes } from 'react';
import { Button } from './Button';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

/**
 * Pagination props
 */
export interface PaginationProps extends HTMLAttributes<HTMLElement> {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  maxVisiblePages?: number;
  showEllipsis?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Pagination component
 * Docs: https://daisyui.com/components/pagination/
 */
export const Pagination = forwardRef<HTMLElement, PaginationProps>(({
  currentPage,
  totalPages,
  onPageChange,
  maxVisiblePages = 5,
  showEllipsis = false,
  size = 'md',
  className = '',
  ...props
}, ref) => {
  if (totalPages <= 1) return null;

  // daisyUI v5: size is expressed on the buttons; the join wrapper is uniform.
  const buttonSize = {
    sm: 'btn-sm',
    md: 'btn-md',
    lg: 'btn-lg',
  };

  // Calculate visible page range or ellipsis items
  const getPageItems = (): (number | 'ellipsis-start' | 'ellipsis-end')[] => {
    if (!showEllipsis || totalPages <= maxVisiblePages) {
      const half = Math.floor(maxVisiblePages / 2);
      let start = Math.max(1, currentPage - half);
      let end = Math.min(totalPages, start + maxVisiblePages - 1);

      // Adjust if we're at the end
      if (end - start + 1 < maxVisiblePages) {
        start = Math.max(1, end - maxVisiblePages + 1);
      }

      // Adjust if we're at the beginning
      if (end - start + 1 < maxVisiblePages) {
        end = Math.min(totalPages, start + maxVisiblePages - 1);
      }

      return Array.from({ length: end - start + 1 }, (_, i) => start + i);
    }

    const items: (number | 'ellipsis-start' | 'ellipsis-end')[] = [];
    const windowStart = Math.max(2, currentPage - 1);
    const windowEnd = Math.min(totalPages - 1, currentPage + 1);

    items.push(1);
    if (windowStart > 2) {
      items.push('ellipsis-start');
    }
    for (let p = windowStart; p <= windowEnd; p++) {
      items.push(p);
    }
    if (windowEnd < totalPages - 1) {
      items.push('ellipsis-end');
    }
    items.push(totalPages);

    return items;
  };

  const pageItems = getPageItems();

  return (
    <nav
      ref={ref}
      aria-label="Pagination"
      className={`flex items-center justify-center gap-2 ${className}`.trim()}
      {...props}
    >
      {/* First page button */}
      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(1)}
        disabled={currentPage === 1}
        className={buttonSize[size]}
        aria-label="First page"
      >
        <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
      </Button>

      {/* Previous page button */}
      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className={buttonSize[size]}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </Button>

      {/* Page numbers */}
      <div className="join">
        {pageItems.map((item) => {
          if (typeof item === 'string') {
            return (
              <button
                type="button"
                key={item}
                disabled
                className={`btn btn-disabled ${buttonSize[size]}`}
                aria-hidden="true"
              >
                ...
              </button>
            );
          }
          return (
            <button
              type="button"
              key={item}
              className={`btn ${buttonSize[size]} ${currentPage === item ? 'btn-active' : ''}`}
              onClick={() => onPageChange(item)}
              aria-current={currentPage === item ? 'page' : undefined}
              aria-label={`Page ${item}`}
            >
              {item}
            </button>
          );
        })}
      </div>

      {/* Next page button */}
      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className={buttonSize[size]}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>

      {/* Last page button */}
      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(totalPages)}
        disabled={currentPage === totalPages}
        className={buttonSize[size]}
        aria-label="Last page"
      >
        <ChevronsRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </nav>
  );
});

Pagination.displayName = 'Pagination';

/**
 * Simple Pagination with just previous/next buttons
 */
export interface SimplePaginationProps extends HTMLAttributes<HTMLElement> {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const SimplePagination = forwardRef<HTMLElement, SimplePaginationProps>(({
  currentPage,
  totalPages,
  onPageChange,
  size = 'md',
  className = '',
  ...props
}, ref) => {
  if (totalPages <= 1) return null;

  const buttonSize = {
    sm: 'btn-sm',
    md: 'btn-md',
    lg: 'btn-lg',
  };

  return (
    <nav
      ref={ref}
      aria-label="Pagination"
      className={`flex items-center justify-center gap-2 ${className}`.trim()}
      {...props}
    >
      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className={buttonSize[size]}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        Previous
      </Button>

      <span className="px-4 py-2 text-sm" aria-live="polite">
        Page {currentPage} of {totalPages}
      </span>

      <Button
        variant="outline"
        size={size}
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className={buttonSize[size]}
        aria-label="Next page"
      >
        Next
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </nav>
  );
});

SimplePagination.displayName = 'SimplePagination';

/**
 * Pagination with item count and page size selector
 */
export interface AdvancedPaginationProps extends HTMLAttributes<HTMLDivElement> {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems: number;
  itemsPerPage: number;
  onItemsPerPageChange: (itemsPerPage: number) => void;
  itemsPerPageOptions?: number[];
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const AdvancedPagination = forwardRef<HTMLDivElement, AdvancedPaginationProps>(({
  currentPage,
  totalPages,
  onPageChange,
  totalItems,
  itemsPerPage,
  onItemsPerPageChange,
  itemsPerPageOptions = [10, 25, 50, 100],
  size = 'md',
  className = '',
  ...props
}, ref) => {
  if (totalPages <= 1) return null;

  return (
    <div
      ref={ref}
      className={`flex flex-col sm:flex-row items-center justify-between gap-4 ${className}`.trim()}
      {...props}
    >
      <div className="text-sm text-base-content/70" aria-live="polite">
        Showing {(currentPage - 1) * itemsPerPage + 1} to{' '}
        {Math.min(currentPage * itemsPerPage, totalItems)} of {totalItems} items
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="pagination-items-per-page" className="text-sm text-base-content/70">
          Items per page:
        </label>
        <select
          id="pagination-items-per-page"
          className="select select-bordered select-sm"
          value={itemsPerPage}
          onChange={(e) => onItemsPerPageChange(Number(e.target.value))}
        >
          {itemsPerPageOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </div>

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={onPageChange}
        size={size}
      />
    </div>
  );
});

AdvancedPagination.displayName = 'AdvancedPagination';

/**
 * Pagination hook for managing pagination state
 */
export const usePagination = (
  initialPage: number = 1,
  initialItemsPerPage: number = 10
) => {
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [itemsPerPage, setItemsPerPage] = useState(initialItemsPerPage);

  const goToPage = (page: number) => {
    setCurrentPage(Math.max(1, page));
  };

  const goToNext = () => {
    setCurrentPage(currentPage + 1);
  };

  const goToPrevious = () => {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1);
    }
  };

  const goToFirst = () => {
    setCurrentPage(1);
  };

  const goToLast = (totalPages: number) => {
    setCurrentPage(totalPages);
  };

  const setItemsPerPageHandler = (items: number) => {
    setItemsPerPage(items);
    setCurrentPage(1); // Reset to first page when changing items per page
  };

  // Calculate total pages based on total items
  const calculateTotalPages = (totalItems: number) => {
    return Math.ceil(totalItems / itemsPerPage);
  };

  // Get current page items
  const getCurrentPageItems = <T,>(items: T[]) => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return items.slice(startIndex, startIndex + itemsPerPage);
  };

  return {
    currentPage,
    itemsPerPage,
    goToPage,
    goToNext,
    goToPrevious,
    goToFirst,
    goToLast,
    setItemsPerPage: setItemsPerPageHandler,
    calculateTotalPages,
    getCurrentPageItems,
    setCurrentPage,
  };
};

/**
 * Infinite scroll pagination hook
 */
export const useInfiniteScroll = <T,>(
  initialItems: T[] = [],
  itemsPerPage: number = 10
) => {
  const [items, setItems] = useState<T[]>(initialItems);
  const [hasMore, setHasMore] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [page, setPage] = useState(1);

  const isEmpty = items.length === 0 && !hasMore && !isLoading && !error;

  const loadMore = async (fetchFunction: (page: number, itemsPerPage: number) => Promise<T[]>) => {
    if (isLoading || !hasMore) return;

    setIsLoading(true);
    setError(null);
    try {
      const newItems = await fetchFunction(page + 1, itemsPerPage);
      
      if (newItems.length === 0) {
        setHasMore(false);
      } else {
        setItems(prev => [...prev, ...newItems]);
        setPage(prev => prev + 1);
      }
    } catch (err: unknown) {
      console.error('Error loading more items:', err);
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  };

  const reset = () => {
    setItems(initialItems);
    setHasMore(true);
    setError(null);
    setPage(1);
  };

  return {
    items,
    hasMore,
    isLoading,
    error,
    isEmpty,
    loadMore,
    reset,
    setItems,
  };
};

const PaginationComponents = {
  Pagination,
  SimplePagination,
  AdvancedPagination,
  usePagination,
  useInfiniteScroll,
};

export default PaginationComponents;
