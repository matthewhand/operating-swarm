import { useState, useRef, useEffect, ReactNode, MouseEvent, SyntheticEvent, forwardRef, HTMLAttributes, DetailsHTMLAttributes } from 'react';

/**
 * Tab interface
 */
export interface Tab {
  key: string;
  label: ReactNode;
  disabled?: boolean;
  icon?: ReactNode;
}

/**
 * Tabs component props
 */
export interface TabsProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabKey: string) => void;
  variant?: 'boxed' | 'lifted' | 'bordered';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Tabs component
 * Docs: https://daisyui.com/components/tabs/
 */
export const Tabs = forwardRef<HTMLDivElement, TabsProps>(({
  tabs,
  activeTab,
  onChange,
  variant = 'boxed',
  size = 'md',
  className = '',
  ...props
}, ref) => {
  const variantClasses = {
    // daisyUI v5 renamed: boxed→tabs-box, lifted→tabs-lift, bordered→tabs-border.
    boxed: 'tabs-box',
    lifted: 'tabs-lift',
    bordered: 'tabs-border',
  };

  const sizeClasses = {
    sm: 'tabs-sm',
    md: 'tabs-md',
    lg: 'tabs-lg',
  };

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let newIndex = index;
    let step = 0;

    if (e.key === 'ArrowRight') {
      newIndex = index + 1 >= tabs.length ? 0 : index + 1;
      step = 1;
    } else if (e.key === 'ArrowLeft') {
      newIndex = index - 1 < 0 ? tabs.length - 1 : index - 1;
      step = -1;
    } else if (e.key === 'Home') {
      newIndex = 0;
      step = 1;
    } else if (e.key === 'End') {
      newIndex = tabs.length - 1;
      step = -1;
    }

    if (step !== 0 && newIndex !== index) {
      e.preventDefault();
      let count = 0;
      while (tabs[newIndex].disabled && count < tabs.length) {
        newIndex = step === 1
          ? (newIndex + 1 >= tabs.length ? 0 : newIndex + 1)
          : (newIndex - 1 < 0 ? tabs.length - 1 : newIndex - 1);
        count++;
      }

      if (!tabs[newIndex].disabled) {
        onChange(tabs[newIndex].key);
        const tabElement = tabRefs.current[newIndex];
        if (tabElement) {
          tabElement.focus();
        }
      }
    }
  };

  return (
    <div
      ref={ref}
      className={`tabs ${variantClasses[variant]} ${sizeClasses[size]} ${className}`.trim()}
      role="tablist"
      aria-orientation="horizontal"
      {...props}
    >
      {tabs.map((tab, index) => {
        const isSelected = activeTab === tab.key;
        return (
          <button
            ref={(el) => (tabRefs.current[index] = el)}
            id={`tab-${tab.key}`}
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isSelected}
            aria-controls={`panel-${tab.key}`}
            tabIndex={isSelected ? 0 : -1}
            className={`tab ${isSelected ? 'tab-active' : ''} ${tab.disabled ? 'tab-disabled' : ''}`}
            onClick={() => !tab.disabled && onChange(tab.key)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            disabled={tab.disabled}
          >
            {tab.icon && <span className="mr-2" aria-hidden="true">{tab.icon}</span>}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
});

Tabs.displayName = 'Tabs';

/**
 * Tab Panel component
 */
export interface TabPanelProps extends HTMLAttributes<HTMLDivElement> {
  activeTab: string;
  tabKey: string;
  children: ReactNode;
}

export const TabPanel = forwardRef<HTMLDivElement, TabPanelProps>(({
  activeTab,
  tabKey,
  children,
  className = '',
  ...props
}, ref) => {
  if (activeTab !== tabKey) return null;
  return (
    <div
      ref={ref}
      id={`panel-${tabKey}`}
      role="tabpanel"
      aria-labelledby={`tab-${tabKey}`}
      tabIndex={0}
      className={`tab-content p-4 ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  );
});

TabPanel.displayName = 'TabPanel';

/**
 * Simple Tabs component with built-in state management
 */
export const SimpleTabs = ({
  tabs,
  children,
  variant = 'boxed',
  size = 'md',
  className = '',
}: {
  tabs: Tab[];
  children: ReactNode;
  variant?: 'boxed' | 'lifted' | 'bordered';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}) => {
  const [activeTab, setActiveTab] = useState(tabs[0]?.key || '');

  return (
    <>
      <Tabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
        variant={variant}
        size={size}
        className={className}
      />
      {children}
    </>
  );
};

/**
 * Accordion component
 * Docs: https://daisyui.com/components/accordion/
 */
export interface AccordionItemType {
  key: string;
  title: ReactNode;
  content: ReactNode;
  disabled?: boolean;
  icon?: ReactNode;
}

export interface AccordionProps extends HTMLAttributes<HTMLDivElement> {
  items: AccordionItemType[];
  allowMultiple?: boolean;
  className?: string;
}

export const Accordion = forwardRef<HTMLDivElement, AccordionProps>(({
  items,
  allowMultiple = false,
  className = '',
  ...props
}, ref) => {
  const [activeItems, setActiveItems] = useState<string[]>([]);

  const toggleItem = (key: string, disabled: boolean, event: MouseEvent<HTMLElement>) => {
    event.preventDefault();
    if (disabled) return;

    if (allowMultiple) {
      setActiveItems(prev =>
        prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      );
    } else {
      setActiveItems(prev => prev.includes(key) ? [] : [key]);
    }
  };

  return (
    <div ref={ref} className={`join join-vertical w-full ${className}`.trim()} {...props}>
      {items.map((item) => {
        const isOpen = activeItems.includes(item.key);
        return (
          <details
            key={item.key}
            className={`collapse collapse-arrow join-item border border-base-300 ${item.disabled ? 'opacity-50 pointer-events-none' : ''}`}
            open={isOpen}
          >
            <summary
              className="collapse-title font-medium flex items-center gap-2 cursor-pointer"
              onClick={(event) => toggleItem(item.key, Boolean(item.disabled), event)}
            >
              {item.icon && <span>{item.icon}</span>}
              {item.title}
            </summary>
            <div className="collapse-content">
              <div className="p-4">
                {item.content}
              </div>
            </div>
          </details>
        );
      })}
    </div>
  );
});

Accordion.displayName = 'Accordion';

/**
 * Accordion Item component (for uncontrolled usage)
 */
export interface AccordionItemProps extends Omit<DetailsHTMLAttributes<HTMLDetailsElement>, 'title'> {
  title: ReactNode;
  children: ReactNode;
  open?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  className?: string;
}

export const AccordionItem = forwardRef<HTMLDetailsElement, AccordionItemProps>(({
  title,
  children,
  open = false,
  disabled = false,
  icon,
  className = '',
  ...props
}, ref) => {
  const [isOpen, setIsOpen] = useState(open);

  useEffect(() => {
    setIsOpen(open);
  }, [open]);

  const handleToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (disabled) {
      event.currentTarget.open = isOpen;
      return;
    }
    setIsOpen(event.currentTarget.open);
  };

  return (
    <details
      ref={ref}
      className={`collapse collapse-arrow join-item border border-base-300 ${disabled ? 'opacity-50 pointer-events-none' : ''} ${className}`.trim()}
      open={isOpen}
      onToggle={handleToggle}
      {...props}
    >
      <summary className="collapse-title font-medium flex items-center gap-2 cursor-pointer">
        {icon && <span>{icon}</span>}
        {title}
      </summary>
      <div className="collapse-content">
        <div className="p-4">
          {children}
        </div>
      </div>
    </details>
  );
});

AccordionItem.displayName = 'AccordionItem';

/**
 * Stepper/Tabs combination for multi-step forms
 */
export interface StepperProps extends HTMLAttributes<HTMLDivElement> {
  steps: Tab[];
  activeStep: number;
  onStepChange: (stepIndex: number) => void;
  className?: string;
}

export const Stepper = forwardRef<HTMLDivElement, StepperProps>(({
  steps,
  activeStep,
  onStepChange,
  className = '',
  ...props
}, ref) => {
  return (
    <div ref={ref} className={`flex items-center justify-between mb-8 ${className}`.trim()} {...props}>
      <div className="flex items-center gap-4">
        {steps.map((step, index) => (
          <button
            key={step.key}
            type="button"
            className={`btn btn-sm ${activeStep === index ? 'btn-primary' : 'btn-ghost'} ${activeStep > index ? 'btn-success' : ''}`}
            onClick={() => onStepChange(index)}
            disabled={activeStep < index}
          >
            {step.icon && <span className="mr-1">{step.icon}</span>}
            {step.label}
          </button>
        ))}
      </div>
      <div className="text-sm text-base-content/70">
        Step {activeStep + 1} of {steps.length}
      </div>
    </div>
  );
});

Stepper.displayName = 'Stepper';

/**
 * Enhanced Tabs with content
 */
export interface ContentTab extends Tab {
  content: ReactNode;
}

/**
 * Vertical Tabs component
 */
export interface VerticalTabsProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  tabs: ContentTab[];
  activeTab: string;
  onChange: (tabKey: string) => void;
  className?: string;
}

export const VerticalTabs = forwardRef<HTMLDivElement, VerticalTabsProps>(({
  tabs,
  activeTab,
  onChange,
  className = '',
  ...props
}, ref) => {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let newIndex = index;
    let step = 0;

    if (e.key === 'ArrowDown') {
      newIndex = index + 1 >= tabs.length ? 0 : index + 1;
      step = 1;
    } else if (e.key === 'ArrowUp') {
      newIndex = index - 1 < 0 ? tabs.length - 1 : index - 1;
      step = -1;
    } else if (e.key === 'Home') {
      newIndex = 0;
      step = 1;
    } else if (e.key === 'End') {
      newIndex = tabs.length - 1;
      step = -1;
    }

    if (step !== 0 && newIndex !== index) {
      e.preventDefault();
      let count = 0;
      while (tabs[newIndex].disabled && count < tabs.length) {
        newIndex = step === 1
          ? (newIndex + 1 >= tabs.length ? 0 : newIndex + 1)
          : (newIndex - 1 < 0 ? tabs.length - 1 : newIndex - 1);
        count++;
      }

      if (!tabs[newIndex].disabled) {
        onChange(tabs[newIndex].key);
        tabRefs.current[newIndex]?.focus();
      }
    }
  };

  return (
    <div ref={ref} className={`flex gap-4 ${className}`.trim()} {...props}>
      <div
        className="flex flex-col gap-1 min-w-[120px]"
        role="tablist"
        aria-orientation="vertical"
      >
        {tabs.map((tab, index) => {
          const isSelected = activeTab === tab.key;
          return (
            <button
              ref={(el) => { tabRefs.current[index] = el; }}
              id={`tab-${tab.key}`}
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls={`panel-${tab.key}`}
              tabIndex={isSelected ? 0 : -1}
              className={`btn btn-sm ${isSelected ? 'btn-active' : ''} ${tab.disabled ? 'btn-disabled' : ''}`}
              onClick={() => !tab.disabled && onChange(tab.key)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              disabled={tab.disabled}
            >
              {tab.icon && <span className="mr-2" aria-hidden="true">{tab.icon}</span>}
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="flex-1">
        {tabs.map((tab) => (
          <TabPanel key={tab.key} activeTab={activeTab} tabKey={tab.key}>
            {tab.content}
          </TabPanel>
        ))}
      </div>
    </div>
  );
});

VerticalTabs.displayName = 'VerticalTabs';

export interface ContentTabsProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  tabs: ContentTab[];
  activeTab: string;
  onChange: (tabKey: string) => void;
  variant?: 'boxed' | 'lifted' | 'bordered';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const ContentTabs = forwardRef<HTMLDivElement, ContentTabsProps>(({
  tabs,
  activeTab,
  onChange,
  variant = 'boxed',
  size = 'md',
  className = '',
  ...props
}, ref) => {
  return (
    <div ref={ref} className={className} {...props}>
      <Tabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={onChange}
        variant={variant}
        size={size}
      />
      <div className="mt-4">
        {tabs.map((tab) => (
          <TabPanel key={tab.key} activeTab={activeTab} tabKey={tab.key}>
            {tab.content}
          </TabPanel>
        ))}
      </div>
    </div>
  );
});

ContentTabs.displayName = 'ContentTabs';

const TabsComponents = {
  Tabs,
  TabPanel,
  SimpleTabs,
  Accordion,
  AccordionItem,
  Stepper,
  VerticalTabs,
  ContentTabs,
};

export default TabsComponents;
