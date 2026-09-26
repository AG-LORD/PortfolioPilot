"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
    <main className="page-shell auth-shell">
      <section className="card auth-panel">
        <span className="eyebrow">PortfolioPilot</span>
        <h1 className="page-title">Create your account</h1>
        <p className="page-subtitle">Start managing a portfolio with risk in view.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field-group">
            <span className="field-label">Email</span>
            <input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="field-group">
            <span className="field-label">Password</span>
            <input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          {error && <p className="notice error" role="alert">{error}</p>}
          {message && <p className="notice success" role="status">{message}</p>}
          <button type="submit" className="primary-button" disabled={submitting}>
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>
        <p className="auth-switch">Already have an account? <Link href="/login">Log in</Link></p>
      </section>
    </main>
  );
}