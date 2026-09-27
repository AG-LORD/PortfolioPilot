"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AUTH_INPUT, AuthField, AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/primitives";
import { createClient } from "@/lib/supabase/client";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);
    try {
      const { data, error: signUpError } = await createClient().auth.signUp({ email, password });
      if (signUpError) {
        setError(signUpError.message);
      } else if (data.session) {
        router.push("/dashboard");
      } else {
        setMessage("Check your email to confirm your account, then log in.");
      }
    } catch {
      setError("Account creation is currently unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start managing a portfolio with risk in view."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-primary hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <AuthField label="Email">
          <input className={AUTH_INPUT} type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </AuthField>
        <AuthField label="Password">
          <input
            className={AUTH_INPUT}
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </AuthField>
        {error && <Notice tone="error">{error}</Notice>}
        {message && <Notice tone="success">{message}</Notice>}
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
