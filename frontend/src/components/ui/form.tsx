/**
 * Form primitives — patrón estándar shadcn/ui sobre react-hook-form.
 *
 * Exporta:
 *   - Form (alias FormProvider de RHF)
 *   - FormField (Controller con contexto del nombre del campo)
 *   - FormItem  (contenedor con id único y vertical stack)
 *   - FormLabel (Label conectado al input vía htmlFor)
 *   - FormControl (Slot que recibe los aria-* + id correctos)
 *   - FormDescription (texto auxiliar id-conectado a aria-describedby)
 *   - FormMessage (mensaje de error o de prop children)
 *
 * Toda la conexión id/aria-* se hace via dos contextos para mantener una
 * sola fuente de verdad por field.
 */
import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { Slot } from "@radix-ui/react-slot";
import {
  Controller,
  FormProvider,
  useFormContext,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";

import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";

const Form = FormProvider;

// ---------------------------------------------------------------------------
// FormField — Controller con contexto de `name`
// ---------------------------------------------------------------------------

type FormFieldContextValue<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  name: TName;
};

const FormFieldContext = React.createContext<FormFieldContextValue | undefined>(
  undefined,
);

function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>(props: ControllerProps<TFieldValues, TName>) {
  return (
    <FormFieldContext.Provider value={{ name: props.name }}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// useFormField — hook helper interno
// ---------------------------------------------------------------------------

function useFormField() {
  const fieldContext = React.useContext(FormFieldContext);
  const itemContext = React.useContext(FormItemContext);
  const formContext = useFormContext();
  if (!fieldContext) {
    throw new Error("useFormField must be used within <FormField>");
  }
  if (!itemContext) {
    throw new Error("useFormField must be used within <FormItem>");
  }
  if (!formContext) {
    throw new Error("useFormField must be used within a <Form> provider");
  }
  const { getFieldState, formState } = formContext;
  const fieldState = getFieldState(fieldContext.name, formState);

  const { id } = itemContext;
  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  };
}

// ---------------------------------------------------------------------------
// FormItem — contenedor con id único
// ---------------------------------------------------------------------------

type FormItemContextValue = { id: string };
const FormItemContext = React.createContext<FormItemContextValue | undefined>(
  undefined,
);

const FormItem = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const id = React.useId();
  return (
    <FormItemContext.Provider value={{ id }}>
      <div ref={ref} className={cn("space-y-1.5", className)} {...props} />
    </FormItemContext.Provider>
  );
});
FormItem.displayName = "FormItem";

// ---------------------------------------------------------------------------
// FormLabel
// ---------------------------------------------------------------------------

const FormLabel = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => {
  const { error, formItemId } = useFormField();
  return (
    <Label
      ref={ref}
      htmlFor={formItemId}
      className={cn(error && "text-red-600", className)}
      {...props}
    />
  );
});
FormLabel.displayName = "FormLabel";

// ---------------------------------------------------------------------------
// FormControl — Slot que recibe id + aria-*
// ---------------------------------------------------------------------------

const FormControl = React.forwardRef<
  React.ElementRef<typeof Slot>,
  React.ComponentPropsWithoutRef<typeof Slot>
>(({ ...props }, ref) => {
  const { error, formItemId, formDescriptionId, formMessageId } =
    useFormField();
  return (
    <Slot
      ref={ref}
      id={formItemId}
      aria-describedby={
        !error
          ? `${formDescriptionId}`
          : `${formDescriptionId} ${formMessageId}`
      }
      aria-invalid={!!error}
      {...props}
    />
  );
});
FormControl.displayName = "FormControl";

// ---------------------------------------------------------------------------
// FormDescription
// ---------------------------------------------------------------------------

const FormDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => {
  const { formDescriptionId } = useFormField();
  return (
    <p
      ref={ref}
      id={formDescriptionId}
      className={cn("text-xs text-mid-gray", className)}
      {...props}
    />
  );
});
FormDescription.displayName = "FormDescription";

// ---------------------------------------------------------------------------
// FormMessage
// ---------------------------------------------------------------------------

const FormMessage = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, children, ...props }, ref) => {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error?.message ?? "") : children;
  if (!body) return null;
  return (
    <p
      ref={ref}
      id={formMessageId}
      className={cn("text-xs font-medium text-red-600", className)}
      {...props}
    >
      {body}
    </p>
  );
});
FormMessage.displayName = "FormMessage";

export {
  useFormField,
  Form,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  FormField,
};
