import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Accordion, AccordionItem, Tabs, TabPanel, Stepper, VerticalTabs, ContentTabs } from '../Tabs';

describe('Tabs Keyboard Navigation', () => {
  const tabs = [
    { key: 'tab1', label: 'Tab 1' },
    { key: 'tab2', label: 'Tab 2' },
    { key: 'tab3', label: 'Tab 3', disabled: true },
    { key: 'tab4', label: 'Tab 4' },
  ];

  it('navigates with ArrowRight, skipping disabled tabs', () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} activeTab="tab1" onChange={onChange} />);

    const firstTab = screen.getByRole('tab', { name: 'Tab 1' });
    fireEvent.keyDown(firstTab, { key: 'ArrowRight' });

    expect(onChange).toHaveBeenCalledWith('tab2');

    // Simulate active tab moved to tab2, arrow right should skip tab3
    render(<Tabs tabs={tabs} activeTab="tab2" onChange={onChange} />);
    const secondTab = screen.getAllByRole('tab', { name: 'Tab 2' })[1] || screen.getAllByRole('tab', { name: 'Tab 2' })[0];
    fireEvent.keyDown(secondTab, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('tab4');
  });

  it('navigates with Home and End', () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} activeTab="tab2" onChange={onChange} />);

    const secondTab = screen.getByRole('tab', { name: 'Tab 2' });
    fireEvent.keyDown(secondTab, { key: 'Home' });
    expect(onChange).toHaveBeenCalledWith('tab1');

    fireEvent.keyDown(secondTab, { key: 'End' });
    expect(onChange).toHaveBeenCalledWith('tab4');
  });
});

describe('VerticalTabs Keyboard Navigation', () => {
  const tabs = [
    { key: 'tab1', label: 'Tab 1', content: <p>One</p> },
    { key: 'tab2', label: 'Tab 2', content: <p>Two</p> },
    { key: 'tab3', label: 'Tab 3', content: <p>Three</p>, disabled: true },
    { key: 'tab4', label: 'Tab 4', content: <p>Four</p> },
  ];

  it('exposes a vertical tablist and moves with ArrowDown, skipping disabled', () => {
    const onChange = vi.fn();
    render(<VerticalTabs tabs={tabs} activeTab="tab1" onChange={onChange} />);

    expect(screen.getByRole('tablist')).toHaveAttribute('aria-orientation', 'vertical');

    const firstTab = screen.getByRole('tab', { name: 'Tab 1' });
    fireEvent.keyDown(firstTab, { key: 'ArrowDown' });
    expect(onChange).toHaveBeenCalledWith('tab2');

    render(<VerticalTabs tabs={tabs} activeTab="tab2" onChange={onChange} />);
    const secondTabs = screen.getAllByRole('tab', { name: 'Tab 2' });
    const secondTab = secondTabs[secondTabs.length - 1];
    fireEvent.keyDown(secondTab, { key: 'ArrowDown' });
    expect(onChange).toHaveBeenCalledWith('tab4');
  });
});

describe('Accordion semantic details/summary', () => {
  it('toggles a details element from the summary click', () => {
    render(
      <Accordion
        items={[
          { key: 'alpha', title: 'Section Alpha', content: 'Alpha body' },
          { key: 'beta', title: 'Section Beta', content: 'Beta body' },
        ]}
      />,
    );

    const summary = screen.getByText('Section Alpha');
    // eslint-disable-next-line testing-library/no-node-access
    const details = summary.closest('details');
    expect(details).toBeTruthy();
    expect(details).not.toHaveAttribute('open');

    fireEvent.click(summary);
    expect(details).toHaveAttribute('open');
    expect(screen.getByText('Alpha body')).toBeInTheDocument();
  });

  it('does not open a disabled item', () => {
    render(
      <Accordion
        items={[
          { key: 'locked', title: 'Locked section', content: 'Secret', disabled: true },
        ]}
      />,
    );

    const summary = screen.getByText('Locked section');
    fireEvent.click(summary);
    // eslint-disable-next-line testing-library/no-node-access
    expect(summary.closest('details')).not.toHaveAttribute('open');
  });

  it('renders AccordionItem as details/summary', () => {
    render(
      <AccordionItem title="Standalone" open>
        Item body
      </AccordionItem>,
    );

    const summary = screen.getByText('Standalone');
    // eslint-disable-next-line testing-library/no-node-access
    expect(summary.closest('details')).toHaveAttribute('open');
    expect(screen.getByText('Item body')).toBeInTheDocument();
  });
});

describe('Tabs variants, sizes, and ref forwarding', () => {
  const tabs = [
    { key: 't1', label: 'Tab One' },
    { key: 't2', label: 'Tab Two' },
  ];

  it('forwards ref and applies variant/size classes', () => {
    const ref = createRef<HTMLDivElement>();
    const { rerender } = render(
      <Tabs
        ref={ref}
        data-testid="tabs-el"
        tabs={tabs}
        activeTab="t1"
        onChange={vi.fn()}
        variant="lifted"
        size="lg"
      />
    );

    const el = screen.getByTestId('tabs-el');
    expect(ref.current).toBe(el);
    expect(el).toHaveClass('tabs', 'tabs-lift', 'tabs-lg');

    rerender(
      <Tabs
        ref={ref}
        data-testid="tabs-el"
        tabs={tabs}
        activeTab="t1"
        onChange={vi.fn()}
        variant="bordered"
        size="sm"
      />
    );
    expect(el).toHaveClass('tabs-border', 'tabs-sm');
  });

  it('renders TabPanel with ref and conditional rendering', () => {
    const ref = createRef<HTMLDivElement>();
    const { rerender } = render(
      <div>
        <TabPanel ref={ref} activeTab="t1" tabKey="t1" data-testid="panel">
          Panel Content 1
        </TabPanel>
      </div>
    );

    expect(screen.getByTestId('panel')).toBeInTheDocument();
    expect(ref.current).toBe(screen.getByTestId('panel'));

    rerender(
      <div>
        <TabPanel ref={ref} activeTab="t2" tabKey="t1" data-testid="panel">
          Panel Content 1
        </TabPanel>
      </div>
    );
    expect(screen.queryByTestId('panel')).not.toBeInTheDocument();
  });

  it('renders Stepper and handles step transitions', () => {
    const ref = createRef<HTMLDivElement>();
    const onStepChange = vi.fn();
    const steps = [
      { key: 's1', label: 'Setup' },
      { key: 's2', label: 'Configure' },
      { key: 's3', label: 'Review' },
    ];

    render(
      <Stepper
        ref={ref}
        data-testid="stepper"
        steps={steps}
        activeStep={1}
        onStepChange={onStepChange}
      />
    );

    expect(ref.current).toBe(screen.getByTestId('stepper'));
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();

    const setupBtn = screen.getByRole('button', { name: 'Setup' });
    const configureBtn = screen.getByRole('button', { name: 'Configure' });
    const reviewBtn = screen.getByRole('button', { name: 'Review' });

    expect(setupBtn).toHaveClass('btn-success');
    expect(configureBtn).toHaveClass('btn-primary');
    expect(reviewBtn).toBeDisabled();

    fireEvent.click(setupBtn);
    expect(onStepChange).toHaveBeenCalledWith(0);
  });

  it('renders ContentTabs with panels and responds to tab change', () => {
    const onChange = vi.fn();
    const contentTabs = [
      { key: 'c1', label: 'Tab 1', content: <p>Panel 1</p> },
      { key: 'c2', label: 'Tab 2', content: <p>Panel 2</p> },
    ];

    render(
      <ContentTabs
        tabs={contentTabs}
        activeTab="c1"
        onChange={onChange}
      />
    );

    expect(screen.getByText('Panel 1')).toBeInTheDocument();
    expect(screen.queryByText('Panel 2')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Tab 2' }));
    expect(onChange).toHaveBeenCalledWith('c2');
  });
});

