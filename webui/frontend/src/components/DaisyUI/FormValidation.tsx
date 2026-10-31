import React, { ReactNode, useState } from 'react';
import { Input, Select, Textarea } from './';

/**
 * Form validation types and utilities
 */
export type ValidationRule<V = unknown> = {
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: RegExp;
  validate?: (value: V) => boolean | string;
  customMessage?: string;
};

export type FormErrors<T> = {
  [K in keyof T]?: string;
};

export type FormTouched<T> = {
  [K in keyof T]?: boolean;
};

/**
 * Form validation hook
 */
export const useFormValidation = <T extends Record<string, unknown>>(
  initialValues: T,
  validationRules: { [K in keyof T]?: ValidationRule<T[K]> }
) => {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<FormErrors<T>>({});
  const [touched, setTouched] = useState<FormTouched<T>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isValid, setIsValid] = useState(false);

  // Validate a single field
  const validateField = <K extends keyof T>(name: K, value: T[K]) => {
    const rule = validationRules[name];
    let error = '';

    if (rule) {
      // Required validation
      if (rule.required && !value) {
        error = rule.customMessage || 'This field is required';
      }
      // Min length validation
      else if (rule.minLength && value && typeof value === 'string' && value.length < rule.minLength) {
        error = rule.customMessage || `Minimum ${rule.minLength} characters required`;
      }
      // Max length validation
      else if (rule.maxLength && value && typeof value === 'string' && value.length > rule.maxLength) {
        error = rule.customMessage || `Maximum ${rule.maxLength} characters allowed`;
      }
      // Pattern validation
      else if (rule.pattern && value && typeof value === 'string' && !rule.pattern.test(value)) {
        error = rule.customMessage || 'Invalid format';
      }
      // Custom validation
      else if (rule.validate) {
        const result = rule.validate(value);
        if (typeof result === 'string') {
          error = result;
        } else if (result === false) {
          error = rule.customMessage || 'Invalid value';
        }
      }
    }

    return error;
  };

  // Validate entire form
  const validateForm = (overrideValues?: T) => {
    const newErrors: FormErrors<T> = {};
    let valid = true;
    const targetValues = overrideValues ?? values;

    Object.keys(validationRules).forEach((key) => {
      const fieldKey = key as keyof T;
      const error = validateField(fieldKey, targetValues[fieldKey]);
      if (error) {
        newErrors[fieldKey] = error;
        valid = false;
      }
    });

    setErrors(newErrors);
    setIsValid(valid);
    return valid;
  };

  // Handle field change
  const handleChange = <K extends keyof T>(name: K, value: T[K]) => {
    setValues(prev => ({ ...prev, [name]: value }));
    
    // Validate field on change if already touched
    if (touched[name]) {
      const error = validateField(name, value);
      setErrors(prev => ({ ...prev, [name]: error }));
    }
  };

  // Handle blur (mark as touched)
  const handleBlur = (name: keyof T, value?: T[keyof T]) => {
    setTouched(prev => ({ ...prev, [name]: true }));
    
    // Validate field when touched
    const val = value !== undefined ? (value as T[typeof name]) : values[name];
    const error = validateField(name, val);
    setErrors(prev => ({ ...prev, [name]: error }));
  };

  // Handle submit
  const handleSubmit = async (callback: (values: T) => Promise<void> | void) => {
    setIsSubmitting(true);
    
    const isValid = validateForm();
    
    if (isValid) {
      try {
        await callback(values);
      } catch (error) {
        console.error('Form submission error:', error);
        throw error;
      } finally {
        setIsSubmitting(false);
      }
    } else {
      setIsSubmitting(false);
    }
  };

  // Reset form
  const resetForm = () => {
    setValues(initialValues);
    setErrors({});
    setTouched({});
    setIsSubmitting(false);
    setIsValid(false);
  };

  return {
    values,
    errors,
    touched,
    isSubmitting,
    isValid,
    handleChange,
    handleBlur,
    handleSubmit,
    resetForm,
    setValues,
    setErrors,
    validateForm,
    validateField,
  };
};

/**
 * Validated Input component
 */
export interface ValidatedInputProps {
  name: string;
  label?: string;
  type?: string;
  placeholder?: string;
  value: string | number | readonly string[] | undefined;
  error?: string;
  touched?: boolean;
  onChange: (name: string, value: string) => void;
  onBlur: (name: string) => void;
  inputProps?: Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size' | 'color'>;
}

export const ValidatedInput = React.forwardRef<HTMLInputElement, ValidatedInputProps>(({
  name,
  label,
  type = 'text',
  placeholder,
  value,
  error,
  touched,
  onChange,
  onBlur,
  inputProps,
}, ref) => {
  return (
    <Input
      ref={ref}
      label={label}
      type={type}
      placeholder={placeholder}
      value={value}
      error={touched && error ? error : undefined}
      onChange={(e) => onChange(name, e.target.value)}
      onBlur={() => onBlur(name)}
      {...inputProps}
    />
  );
});
ValidatedInput.displayName = 'ValidatedInput';

/**
 * Validated Select component
 */
export interface ValidatedSelectProps {
  name: string;
  label?: string;
  placeholder?: string;
  value: string | number | readonly string[] | undefined;
  error?: string;
  touched?: boolean;
  onChange: (name: string, value: string) => void;
  onBlur: (name: string) => void;
  options: { value: string; label: ReactNode }[];
  selectProps?: Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size' | 'color'>;
}

export const ValidatedSelect = React.forwardRef<HTMLSelectElement, ValidatedSelectProps>(({
  name,
  label,
  placeholder,
  value,
  error,
  touched,
  onChange,
  onBlur,
  options,
  selectProps,
}, ref) => {
  return (
    <Select
      ref={ref}
      label={label}
      value={value}
      error={touched && error ? error : undefined}
      onChange={(e) => onChange(name, e.target.value)}
      onBlur={() => onBlur(name)}
      {...selectProps}
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </Select>
  );
});
ValidatedSelect.displayName = 'ValidatedSelect';

/**
 * Validated Textarea component
 */
export interface ValidatedTextareaProps {
  name: string;
  label?: string;
  placeholder?: string;
  value: string | number | readonly string[] | undefined;
  error?: string;
  touched?: boolean;
  onChange: (name: string, value: string) => void;
  onBlur: (name: string) => void;
  textareaProps?: Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'color'>;
}

export const ValidatedTextarea = React.forwardRef<HTMLTextAreaElement, ValidatedTextareaProps>(({
  name,
  label,
  placeholder,
  value,
  error,
  touched,
  onChange,
  onBlur,
  textareaProps,
}, ref) => {
  return (
    <Textarea
      ref={ref}
      label={label}
      placeholder={placeholder}
      value={value}
      error={touched && error ? error : undefined}
      onChange={(e) => onChange(name, e.target.value)}
      onBlur={() => onBlur(name)}
      {...textareaProps}
    />
  );
});
ValidatedTextarea.displayName = 'ValidatedTextarea';

/**
 * Form component with validation
 */
export interface FormProps<T extends Record<string, unknown>> {
  initialValues: T;
  validationRules: { [K in keyof T]?: ValidationRule<T[K]> };
  onSubmit: (values: T) => Promise<void> | void;
  children: (form: ReturnType<typeof useFormValidation<T>>) => ReactNode;
}

export const Form = <T extends Record<string, unknown>>({
  initialValues,
  validationRules,
  onSubmit,
  children,
}: FormProps<T>) => {
  const form = useFormValidation(initialValues, validationRules);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await form.handleSubmit(onSubmit);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {children(form)}
    </form>
  );
};

const FormValidationComponents = {
  useFormValidation,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
  Form,
};

export default FormValidationComponents;
