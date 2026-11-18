"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { api, ApiRequestError } from "@/lib/api";

const INDUSTRIES = [
  "Manufacturing",
  "Automotive",
  "Food and beverage",
  "Consumer products",
  "Healthcare and life sciences",
  "Logistics",
  "Insurance",
  "Banking",
  "Other",
];

// Zod probes for code generation with new Function, which a strict content security policy reports as a violation.
// The interpreted path is fast enough for a form.
z.config({ jitless: true });

const schema = z.object({
  name: z.string().trim().min(1, "Enter your name").max(120),
  work_email: z.string().trim().email("Enter a valid work email"),
  organization: z.string().trim().min(1, "Enter your organization").max(160),
  role: z.string().trim().max(120).optional(),
  industry: z.string().max(120).optional(),
  message: z.string().max(2000, "Keep the message under 2,000 characters").optional(),
  consent: z.boolean().refine((v) => v, "Consent is required to submit the form"),
});
type Values = z.infer<typeof schema>;

export function ContactForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { work_email: params.get("email") ?? "", consent: false },
  });

  async function onSubmit(v: Values) {
    setError("");
    try {
      await api("/contact/demo-request", {
        json: {
          ...v,
          role: v.role || null,
          industry: v.industry || null,
          message: v.message || null,
        },
      });
      router.push("/contact/thanks");
    } catch (e) {
      setError(
        e instanceof ApiRequestError && e.status === 429
          ? "Too many requests from this address. Try again later."
          : "The request could not be sent. Check the fields and try again.",
      );
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id="name" label="Name" error={errors.name?.message}>
          {(a) => <Input {...a} autoComplete="name" {...register("name")} />}
        </Field>
        <Field id="work_email" label="Work email" error={errors.work_email?.message}>
          {(a) => <Input {...a} type="email" autoComplete="email" {...register("work_email")} />}
        </Field>
        <Field id="organization" label="Organization" error={errors.organization?.message}>
          {(a) => <Input {...a} autoComplete="organization" {...register("organization")} />}
        </Field>
        <Field id="role" label="Role (optional)" error={errors.role?.message}>
          {(a) => <Input {...a} autoComplete="organization-title" {...register("role")} />}
        </Field>
      </div>
      <Field id="industry" label="Industry (optional)">
        {(a) => (
          <Select {...a} {...register("industry")} defaultValue="">
            <option value="">Select an industry</option>
            {INDUSTRIES.map((i) => (
              <option key={i}>{i}</option>
            ))}
          </Select>
        )}
      </Field>
      <Field
        id="message"
        label="Message (optional)"
        error={errors.message?.message}
        hint="What would you like to see?"
      >
        {(a) => <Textarea {...a} {...register("message")} />}
      </Field>
      <div>
        <div className="flex gap-3">
          <Checkbox
            id="consent"
            aria-describedby={errors.consent ? "consent-error" : undefined}
            aria-invalid={errors.consent ? true : undefined}
            {...register("consent")}
          />
          <label htmlFor="consent" className="text-[15px] leading-6 text-slate-700">
            I agree that my details are stored and used to respond to this request, as described in
            the privacy policy.
          </label>
        </div>
        {errors.consent && (
          <p id="consent-error" role="alert" className="text-danger mt-1.5 text-sm">
            {errors.consent.message}
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="rounded-[8px] bg-[#fbe4e1] p-3 text-sm text-[#9b2c20]">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={isSubmitting}>
        {isSubmitting ? "Sending" : "Request a demo"}
      </Button>
    </form>
  );
}
