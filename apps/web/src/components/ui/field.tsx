import * as React from "react";
import { cn } from "@/lib/cn";

const control =
  "w-full rounded-[8px] border border-slate-300 bg-white px-3 text-[15px] text-ink placeholder:text-slate-500 focus-visible:border-brand-500 focus-visible:outline-2 focus-visible:outline-brand-500 disabled:bg-slate-100 aria-[invalid=true]:border-danger";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn(control, "h-11", className)} {...p} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn(control, "min-h-28 py-2.5", className)} {...p} />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...p }, ref) => (
  <select ref={ref} className={cn(control, "h-11", className)} {...p}>
    {children}
  </select>
));
Select.displayName = "Select";

export const Checkbox = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...p }, ref) => (
  <input
    ref={ref}
    type="checkbox"
    className={cn("accent-brand-600 mt-1 size-4 rounded border-slate-400", className)}
    {...p}
  />
));
Checkbox.displayName = "Checkbox";

/** Label, control, hint, and error message wired together for assistive technology. */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: (aria: {
    id: string;
    "aria-describedby"?: string;
    "aria-invalid"?: boolean;
  }) => React.ReactNode;
}) {
  const describedBy =
    [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-ink block text-sm font-medium">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-slate-600">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}
    </div>
  );
}
