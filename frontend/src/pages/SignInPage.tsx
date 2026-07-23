import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { login } from "../api/auth";
import { ApiError } from "../api/client";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Password must contain at least 8 characters."),
});

type FormValues = z.infer<typeof schema>;

function BrandMark() {
  return (
    <span className="auth-brand-mark" aria-hidden="true">
      <span /><span /><span /><span />
    </span>
  );
}

export function SignInPage() {
  const [showPassword, setShowPassword] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => login(values.email, values.password),
    onSuccess: (session) => {
      queryClient.setQueryData(["session"], session);
      const destination = (location.state as { from?: string } | null)?.from ?? "/projects";
      void navigate(destination, { replace: true });
    },
  });
  const submit = form.handleSubmit((values) => mutation.mutate(values));
  const serverMessage =
    mutation.error instanceof ApiError ? mutation.error.problem.detail : undefined;

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Product introduction">
        <div className="auth-brand"><BrandMark /><span>AI Project Manager</span></div>
        <div className="auth-story-copy">
          <span className="auth-kicker">Structured intelligence for delivery</span>
          <h1>Turn ambitious ideas into clear, approved execution.</h1>
          <p>
            Build trustworthy plans, surface dependencies, and understand project health—with
            every important decision kept under your control.
          </p>
          <div className="auth-proof" aria-label="Product principles">
            <span>Deterministic validation</span><span>Approval-first AI</span><span>Evidence-backed insight</span>
          </div>
        </div>
        <div className="auth-visual" aria-hidden="true">
          <span className="auth-node node-a" /><span className="auth-node node-b" /><span className="auth-node node-c" />
          <span className="auth-line line-a" /><span className="auth-line line-b" />
        </div>
      </section>

      <section className="auth-form-panel" aria-labelledby="sign-in-heading">
        <div className="auth-form-wrap">
          <div className="auth-mobile-brand"><BrandMark /><span>AI Project Manager</span></div>
          <span className="eyebrow">Welcome back</span>
          <h2 id="sign-in-heading">Sign in to your workspace</h2>
          <p className="auth-form-intro">Use your project-owner account to continue.</p>
          <form className="auth-form" onSubmit={(event) => void submit(event)} noValidate>
            {serverMessage ? <div className="form-alert" role="alert">{serverMessage}</div> : null}
            <label>
              <span>Email address</span>
              <input type="email" required autoComplete="email" placeholder="name@company.com" aria-invalid={Boolean(form.formState.errors.email)} {...form.register("email")} />
              {form.formState.errors.email ? <small className="field-error">{form.formState.errors.email.message}</small> : null}
            </label>
            <label>
              <span>Password</span>
              <span className="password-field">
                <input type={showPassword ? "text" : "password"} required autoComplete="current-password" placeholder="Enter your password" aria-invalid={Boolean(form.formState.errors.password)} {...form.register("password")} />
                <button type="button" className="password-toggle" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((current) => !current)}>{showPassword ? "Hide" : "Show"}</button>
              </span>
              {form.formState.errors.password ? <small className="field-error">{form.formState.errors.password.message}</small> : null}
            </label>
            <button className="button primary auth-submit" type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Signing in…" : "Sign in securely"}</button>
          </form>
          <p className="auth-security-note">Your session is protected with an HttpOnly cookie and request verification.</p>
        </div>
      </section>
    </main>
  );
}
