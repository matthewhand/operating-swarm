import { render, screen, fireEvent } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import {
  Pagination,
  SimplePagination,
  AdvancedPagination,
  usePagination,
} from '../Pagination';

describe('Pagination Component', () => {
  it('wraps controls in a labelled navigation landmark', () => {
    render(<Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} />);
    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument();
  });

  it('adds aria-current="page" to the active page button', () => {
    const onPageChange = vi.fn();
    render(<Pagination currentPage={2} totalPages={5} onPageChange={onPageChange} />);

    const activeBtn = screen.getByRole('button', { name: 'Page 2' });
    expect(activeBtn).toHaveAttribute('aria-current', 'page');
    expect(activeBtn).toHaveClass('btn-active');

    const inactiveBtn = screen.getByRole('button', { name: 'Page 3' });
    expect(inactiveBtn).not.toHaveAttribute('aria-current', 'page');
  });

  it('returns null if totalPages <= 1', () => {
    const { container } = render(
      <Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('disables First/Previous on page 1 and Next/Last on final page', () => {
    const onPageChange = vi.fn();
    const { rerender } = render(
      <Pagination currentPage={1} totalPages={5} onPageChange={onPageChange} />
    );

    expect(screen.getByRole('button', { name: 'First page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Last page' })).not.toBeDisabled();

    rerender(
      <Pagination currentPage={5} totalPages={5} onPageChange={onPageChange} />
    );

    expect(screen.getByRole('button', { name: 'First page' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Last page' })).toBeDisabled();
  });

  it('triggers onPageChange when navigation buttons are clicked', () => {
    const onPageChange = vi.fn();
    render(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    );

    fireEvent.click(screen.getByRole('button', { name: 'First page' }));
    expect(onPageChange).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(onPageChange).toHaveBeenCalledWith(2);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(4);

    fireEvent.click(screen.getByRole('button', { name: 'Last page' }));
    expect(onPageChange).toHaveBeenCalledWith(5);

    fireEvent.click(screen.getByRole('button', { name: 'Page 4' }));
    expect(onPageChange).toHaveBeenCalledWith(4);
  });

  it('renders ellipsis buttons when showEllipsis is true and totalPages exceeds maxVisiblePages', () => {
    render(
      <Pagination
        currentPage={10}
        totalPages={20}
        maxVisiblePages={5}
        showEllipsis={true}
        onPageChange={vi.fn()}
      />
    );

    const ellipses = screen.getAllByText('...');
    expect(ellipses.length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Page 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page 20' })).toBeInTheDocument();
  });

  it('forwards ref and attributes on Pagination and SimplePagination', () => {
    const pagRef = createRef<HTMLElement>();
    const simpleRef = createRef<HTMLElement>();

    render(
      <div>
        <Pagination
          ref={pagRef}
          data-testid="pag-el"
          currentPage={2}
          totalPages={4}
          onPageChange={vi.fn()}
        />
        <SimplePagination
          ref={simpleRef}
          data-testid="simple-el"
          currentPage={2}
          totalPages={4}
          onPageChange={vi.fn()}
        />
      </div>
    );

    expect(pagRef.current).toBe(screen.getByTestId('pag-el'));
    expect(simpleRef.current).toBe(screen.getByTestId('simple-el'));
  });

  it('renders AdvancedPagination and handles itemsPerPage change', () => {
    const ref = createRef<HTMLDivElement>();
    const onItemsPerPageChange = vi.fn();

    render(
      <AdvancedPagination
        ref={ref}
        data-testid="adv-el"
        currentPage={2}
        totalPages={10}
        totalItems={100}
        itemsPerPage={10}
        onPageChange={vi.fn()}
        onItemsPerPageChange={onItemsPerPageChange}
      />
    );

    expect(ref.current).toBe(screen.getByTestId('adv-el'));
    expect(screen.getByText('Showing 11 to 20 of 100 items')).toBeInTheDocument();

    const select = screen.getByLabelText('Items per page:');
    fireEvent.change(select, { target: { value: '25' } });
    expect(onItemsPerPageChange).toHaveBeenCalledWith(25);
  });

  it('provides working usePagination hook helpers', () => {
    const { result } = renderHook(() => usePagination(1, 10));

    expect(result.current.currentPage).toBe(1);
    expect(result.current.itemsPerPage).toBe(10);
    expect(result.current.calculateTotalPages(45)).toBe(5);

    act(() => {
      result.current.goToNext();
    });
    expect(result.current.currentPage).toBe(2);

    act(() => {
      result.current.goToPrevious();
    });
    expect(result.current.currentPage).toBe(1);

    act(() => {
      result.current.goToLast(10);
    });
    expect(result.current.currentPage).toBe(10);

    act(() => {
      result.current.goToFirst();
    });
    expect(result.current.currentPage).toBe(1);

    act(() => {
      result.current.setItemsPerPage(20);
    });
    expect(result.current.itemsPerPage).toBe(20);
    expect(result.current.currentPage).toBe(1); // resets to 1

    const items = ['a', 'b', 'c', 'd', 'e'];
    expect(result.current.getCurrentPageItems(items)).toEqual(['a', 'b', 'c', 'd', 'e']);
  });
});
