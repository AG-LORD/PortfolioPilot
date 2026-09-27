"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AUTH_INPUT, AuthField, AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/primitives";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const router = useRouter();
  const supabase = createClient();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);

    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      return;
    }

    router.push("/dashboard");
  }

  async function resendConfirmation() {
    setError(null);
    setMessage(null);

    const { error } = await supabase.auth.resend({ type: "signup", email });
    if (error) {
      setError(error.message);
      return;
    }
    setMessage("A new confirmation email has been sent. Open its newest link, then return here to log in.");
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Log in to manage your portfolios."
      footer={
        <>
          New to PortfolioPilot?{" "}
          <Link href="/register" className="font-semibold text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthField label="Email">
          <input
            className={AUTH_INPUT}
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </AuthField>
        <AuthField label="Password">
          <input className={AUTH_INPUT} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </AuthField>
        <Button type="submit" className="w-full">
          Log in
        </Button>
      </form>
      <div className="mt-4 space-y-3">
        {error && <Notice tone="error">{error}</Notice>}
        {error === "Email not confirmed" && (
          <Button variant="outline" className="w-full" onClick={() => void resendConfirmation()}>
            Resend confirmation email
          </Button>
        )}
        {message && <Notice tone="success">{message}</Notice>}
      </div>
    </AuthShell>
  );
}
