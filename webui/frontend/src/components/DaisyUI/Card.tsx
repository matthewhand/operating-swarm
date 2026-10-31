import { ReactNode, forwardRef, HTMLAttributes } from 'react';

/**
 * Card component using DaisyUI 5 classes
 * Docs: https://daisyui.com/components/card/
 */
export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  children?: ReactNode;
  title?: ReactNode;
  bordered?: boolean;
  compact?: boolean;
  normal?: boolean;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  side?: boolean;
  imageFull?: boolean;
  className?: string;
  actions?: ReactNode;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(({
  children,
  title,
  bordered = false,
  compact = false,
  normal = false,
  size,
  side = false,
  imageFull = false,
  className = '',
  actions,
  ...props
}, ref) => {
  // Determine size class
  const resolvedSizeClass =
    size === 'xs' ? 'card-xs' :
    size === 'sm' || compact ? 'card-sm' :
    size === 'lg' || normal ? 'card-lg' :
    size === 'xl' ? 'card-xl' :
    '';

  // Build class list
  const classes = [
    'card',
    // daisyUI 5 renamed `card-bordered` to `card-border`; keep an explicit
    // border class as well for theme token consistency.
    bordered ? 'card-border border border-base-300' : '',
    resolvedSizeClass,
    side ? 'card-side' : '',
    imageFull ? 'image-full' : '',
    className
  ].filter(Boolean);

  return (
    <div ref={ref} className={classes.join(' ')} {...props}>
      <div className="card-body">
        {title && (
          <div className="card-title text-base-content">
            {title}
          </div>
        )}
        {children}
        {actions && (
          <div className="card-actions justify-end mt-2">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
});

Card.displayName = 'Card';

/**
 * Subcomponents for flexible composable cards
 */
export const CardBody = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({
  className = '',
  children,
  ...props
}, ref) => (
  <div ref={ref} className={`card-body ${className}`} {...props}>
    {children}
  </div>
));
CardBody.displayName = 'CardBody';

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(({
  className = '',
  children,
  ...props
}, ref) => (
  <h3 ref={ref} className={`card-title ${className}`} {...props}>
    {children}
  </h3>
));
CardTitle.displayName = 'CardTitle';

export const CardActions = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({
  className = '',
  children,
  ...props
}, ref) => (
  <div ref={ref} className={`card-actions justify-end ${className}`} {...props}>
    {children}
  </div>
));
CardActions.displayName = 'CardActions';

/**
 * Card with image support
 */
export interface ImageCardProps extends CardProps {
  imageSrc?: string;
  imageAlt?: string;
  figureClassName?: string;
}

export const ImageCard = forwardRef<HTMLDivElement, ImageCardProps>(({
  imageSrc,
  imageAlt = '',
  figureClassName = '',
  children,
  ...props
}, ref) => {
  return (
    <Card ref={ref} {...props}>
      {imageSrc && (
        <figure className={figureClassName}>
          <img src={imageSrc} alt={imageAlt} className="w-full h-48 object-cover" />
        </figure>
      )}
      {children}
    </Card>
  );
});

ImageCard.displayName = 'ImageCard';

export default Card;
