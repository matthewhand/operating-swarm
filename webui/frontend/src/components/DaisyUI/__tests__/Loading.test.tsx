import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import {
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
} from '../Loading';

describe('Loading & Skeleton Components', () => {
  it('renders LoadingSpinner with accessible attributes and default classes', () => {
    render(<LoadingSpinner data-testid="spinner" />);
    const el = screen.getByTestId('spinner');
    expect(el).toHaveClass('loading', 'loading-spinner', 'loading-md', 'text-primary');
    expect(el).toHaveAttribute('role', 'status');
    expect(el).toHaveAttribute('aria-label', 'Loading');
    expect(el).toHaveAttribute('aria-live', 'polite');
    expect(el).toHaveAttribute('aria-busy', 'true');
  });

  it('supports custom sizes, colors, and aria-labels on spinners', () => {
    const { rerender } = render(
      <LoadingSpinner size="xs" color="accent" aria-label="Fetching updates" data-testid="s" />
    );
    expect(screen.getByTestId('s')).toHaveClass('loading-xs', 'text-accent');
    expect(screen.getByTestId('s')).toHaveAttribute('aria-label', 'Fetching updates');

    rerender(<LoadingSpinner size="lg" color="current" data-testid="s" />);
    expect(screen.getByTestId('s')).toHaveClass('loading-lg', 'text-current');
  });

  it('renders all loader variants with ref forwarding', () => {
    const sRef = createRef<HTMLSpanElement>();
    const dRef = createRef<HTMLSpanElement>();
    const rRef = createRef<HTMLSpanElement>();
    const bRef = createRef<HTMLSpanElement>();
    const barRef = createRef<HTMLSpanElement>();
    const infRef = createRef<HTMLSpanElement>();

    render(
      <div>
        <LoadingSpinner ref={sRef} data-testid="spinner" />
        <LoadingDots ref={dRef} data-testid="dots" />
        <LoadingRing ref={rRef} data-testid="ring" />
        <LoadingBall ref={bRef} data-testid="ball" />
        <LoadingBars ref={barRef} data-testid="bars" />
        <LoadingInfinity ref={infRef} data-testid="inf" />
      </div>
    );

    expect(screen.getByTestId('spinner')).toHaveClass('loading-spinner');
    expect(sRef.current).toBe(screen.getByTestId('spinner'));

    expect(screen.getByTestId('dots')).toHaveClass('loading-dots');
    expect(dRef.current).toBe(screen.getByTestId('dots'));

    expect(screen.getByTestId('ring')).toHaveClass('loading-ring');
    expect(rRef.current).toBe(screen.getByTestId('ring'));

    expect(screen.getByTestId('ball')).toHaveClass('loading-ball');
    expect(bRef.current).toBe(screen.getByTestId('ball'));

    expect(screen.getByTestId('bars')).toHaveClass('loading-bars');
    expect(barRef.current).toBe(screen.getByTestId('bars'));

    expect(screen.getByTestId('inf')).toHaveClass('loading-infinity');
    expect(infRef.current).toBe(screen.getByTestId('inf'));
  });

  it('renders Skeleton with ref and inline dimensions', () => {
    const ref = createRef<HTMLDivElement>();
    render(<Skeleton ref={ref} width="200px" height="40px" data-testid="skel" />);
    const el = screen.getByTestId('skel');
    expect(ref.current).toBe(el);
    expect(el).toHaveClass('skeleton', 'rounded');
    expect(el).toHaveStyle({ width: '200px', height: '40px' });
  });

  it('renders SkeletonText, SkeletonCard, and SkeletonTable with refs', () => {
    const textRef = createRef<HTMLDivElement>();
    const cardRef = createRef<HTMLDivElement>();
    const tableRef = createRef<HTMLDivElement>();

    render(
      <div>
        <SkeletonText ref={textRef} lines={4} data-testid="text-skel" />
        <SkeletonCard ref={cardRef} data-testid="card-skel" />
        <SkeletonTable ref={tableRef} rows={3} columns={2} data-testid="table-skel" />
      </div>
    );

    expect(textRef.current).toBe(screen.getByTestId('text-skel'));
    expect(cardRef.current).toBe(screen.getByTestId('card-skel'));
    expect(tableRef.current).toBe(screen.getByTestId('table-skel'));

    // Check rows count in table
    const rows = tableRef.current?.querySelectorAll('tbody tr');
    expect(rows?.length).toBe(3);
  });

  it('renders LoadingOverlay conditionally with message', () => {
    const { rerender } = render(
      <LoadingOverlay isLoading={true} message="Processing agent..." data-testid="overlay" />
    );
    expect(screen.getByTestId('overlay')).toBeInTheDocument();
    expect(screen.getByText('Processing agent...')).toBeInTheDocument();

    rerender(<LoadingOverlay isLoading={false} data-testid="overlay" />);
    expect(screen.queryByTestId('overlay')).not.toBeInTheDocument();
  });

  it('renders LoadingButton with ref, disabled state, and spinner', () => {
    const ref = createRef<HTMLButtonElement>();
    const handleClick = vi.fn();
    const { rerender } = render(
      <LoadingButton ref={ref} loading={false} onClick={handleClick}>
        Save changes
      </LoadingButton>
    );

    const btn = screen.getByRole('button', { name: 'Save changes' });
    expect(ref.current).toBe(btn);
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);

    // Switch to loading
    rerender(
      <LoadingButton ref={ref} loading={true} onClick={handleClick}>
        Save changes
      </LoadingButton>
    );

    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Loading')).toHaveClass('sr-only');
    expect(btn.querySelector('.loading-spinner')).toBeInTheDocument();
  });
});
