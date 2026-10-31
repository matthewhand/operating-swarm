import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import {
  Badge,
  PrimaryBadge,
  SuccessBadge,
  WarningBadge,
  ErrorBadge,
  InfoBadge,
  NeutralBadge,
  GhostBadge,
} from '../Badge';

describe('Badge Component', () => {
  it('renders default neutral badge', () => {
    render(<Badge data-testid="badge">Default</Badge>);
    const el = screen.getByTestId('badge');
    expect(el).toHaveClass('badge', 'badge-neutral');
    expect(el).toHaveTextContent('Default');
  });

  it('supports color and legacy type props', () => {
    const { rerender } = render(<Badge color="primary" data-testid="b">Primary</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-primary');

    rerender(<Badge type="secondary" data-testid="b">Secondary</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-secondary');

    // color takes precedence over type if both are passed
    rerender(<Badge color="accent" type="error" data-testid="b">Accent</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-accent');
  });

  it('supports sizes and outline modifier', () => {
    const { rerender } = render(<Badge size="xs" data-testid="b">XS</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-xs');

    rerender(<Badge size="sm" data-testid="b">SM</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-sm');

    rerender(<Badge size="lg" data-testid="b">LG</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-lg');

    rerender(<Badge outline color="primary" data-testid="b">Outline</Badge>);
    expect(screen.getByTestId('b')).toHaveClass('badge-outline');
    expect(screen.getByTestId('b')).not.toHaveClass('badge-primary');
  });

  it('forwards ref and HTML attributes cleanly', () => {
    const ref = createRef<HTMLSpanElement>();
    const handleClick = vi.fn();
    render(
      <Badge
        ref={ref}
        data-testid="b"
        title="Status badge"
        role="status"
        aria-label="Active status"
        onClick={handleClick}
      >
        Active
      </Badge>
    );

    const el = screen.getByTestId('b');
    expect(ref.current).toBe(el);
    expect(el).toHaveAttribute('title', 'Status badge');
    expect(el).toHaveAttribute('role', 'status');
    expect(el).toHaveAttribute('aria-label', 'Active status');

    fireEvent.click(el);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('renders specialized subcomponents with ref forwarding', () => {
    const pRef = createRef<HTMLSpanElement>();
    const sRef = createRef<HTMLSpanElement>();
    const wRef = createRef<HTMLSpanElement>();
    const eRef = createRef<HTMLSpanElement>();
    const iRef = createRef<HTMLSpanElement>();
    const nRef = createRef<HTMLSpanElement>();
    const gRef = createRef<HTMLSpanElement>();

    render(
      <div>
        <PrimaryBadge ref={pRef} data-testid="p">Primary</PrimaryBadge>
        <SuccessBadge ref={sRef} data-testid="s">Success</SuccessBadge>
        <WarningBadge ref={wRef} data-testid="w">Warning</WarningBadge>
        <ErrorBadge ref={eRef} data-testid="e">Error</ErrorBadge>
        <InfoBadge ref={iRef} data-testid="i">Info</InfoBadge>
        <NeutralBadge ref={nRef} data-testid="n">Neutral</NeutralBadge>
        <GhostBadge ref={gRef} data-testid="g">Ghost</GhostBadge>
      </div>
    );

    expect(screen.getByTestId('p')).toHaveClass('badge-primary');
    expect(pRef.current).toBe(screen.getByTestId('p'));

    expect(screen.getByTestId('s')).toHaveClass('badge-success');
    expect(sRef.current).toBe(screen.getByTestId('s'));

    expect(screen.getByTestId('w')).toHaveClass('badge-warning');
    expect(wRef.current).toBe(screen.getByTestId('w'));

    expect(screen.getByTestId('e')).toHaveClass('badge-error');
    expect(eRef.current).toBe(screen.getByTestId('e'));

    expect(screen.getByTestId('i')).toHaveClass('badge-info');
    expect(iRef.current).toBe(screen.getByTestId('i'));

    expect(screen.getByTestId('n')).toHaveClass('badge-neutral');
    expect(nRef.current).toBe(screen.getByTestId('n'));

    expect(screen.getByTestId('g')).toHaveClass('badge-ghost');
    expect(gRef.current).toBe(screen.getByTestId('g'));
  });
});
