import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Card, CardTitle, CardBody, CardActions, ImageCard } from '../Card';

describe('Card Component', () => {
  it('renders card with body and title inside card-body', () => {
    render(
      <Card title="Card Title">
        <p>Card Content</p>
      </Card>
    );
    expect(screen.getByText('Card Title')).toBeInTheDocument();
    expect(screen.getByText('Card Content')).toBeInTheDocument();
    const titleEl = screen.getByText('Card Title');
    expect(titleEl).toHaveClass('card-title');
    expect(titleEl.parentElement).toHaveClass('card-body');
  });

  it('forwards ref and HTML attributes cleanly', () => {
    const ref = createRef<HTMLDivElement>();
    const handleClick = vi.fn();
    render(
      <Card
        ref={ref}
        data-testid="test-card"
        onClick={handleClick}
        aria-label="Accessible Card"
        bordered
      >
        Content
      </Card>
    );

    const card = screen.getByTestId('test-card');
    expect(ref.current).toBe(card);
    expect(card).toHaveAttribute('aria-label', 'Accessible Card');
    expect(card).toHaveClass('card-border');

    fireEvent.click(card);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('applies sizes and variants correctly', () => {
    const { rerender } = render(<Card size="xs" data-testid="c">A</Card>);
    expect(screen.getByTestId('c')).toHaveClass('card-xs');

    rerender(<Card compact data-testid="c">A</Card>);
    expect(screen.getByTestId('c')).toHaveClass('card-sm');

    rerender(<Card size="lg" data-testid="c">A</Card>);
    expect(screen.getByTestId('c')).toHaveClass('card-lg');

    rerender(<Card normal data-testid="c">A</Card>);
    expect(screen.getByTestId('c')).toHaveClass('card-lg');

    rerender(<Card side imageFull data-testid="c">A</Card>);
    expect(screen.getByTestId('c')).toHaveClass('card-side');
    expect(screen.getByTestId('c')).toHaveClass('image-full');
  });

  it('renders actions and custom subcomponents', () => {
    render(
      <Card
        actions={<button type="button">Action Button</button>}
      >
        <p>Text</p>
      </Card>
    );
    expect(screen.getByRole('button', { name: 'Action Button' })).toBeInTheDocument();
  });

  it('supports modular CardBody, CardTitle, and CardActions with refs', () => {
    const titleRef = createRef<HTMLHeadingElement>();
    const bodyRef = createRef<HTMLDivElement>();
    const actionsRef = createRef<HTMLDivElement>();

    render(
      <Card data-testid="modular-card">
        <CardBody ref={bodyRef}>
          <CardTitle ref={titleRef}>Modular Title</CardTitle>
          <p>Body copy</p>
          <CardActions ref={actionsRef}>
            <button type="button">Click</button>
          </CardActions>
        </CardBody>
      </Card>
    );

    expect(titleRef.current).toHaveTextContent('Modular Title');
    expect(bodyRef.current).toHaveClass('card-body');
    expect(actionsRef.current).toHaveClass('card-actions');
  });

  it('renders ImageCard with figure and imageAlt', () => {
    const ref = createRef<HTMLDivElement>();
    render(
      <ImageCard
        ref={ref}
        data-testid="img-card"
        imageSrc="https://example.com/robot.png"
        imageAlt="A friendly robot"
      >
        <p>Robot Card</p>
      </ImageCard>
    );

    const img = screen.getByRole('img', { name: 'A friendly robot' });
    expect(img).toHaveAttribute('src', 'https://example.com/robot.png');
    expect(ref.current).toBe(screen.getByTestId('img-card'));
  });
});
