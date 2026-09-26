"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
    <main className="auth-shell">
      <div className="auth-panel">
        <div className="page-heading">
          <h1 className="page-title">Welcome back</h1>
          <p className="page-subtitle">Log in to manage your portfolios.</p>
        </div>
        <form onSubmit={handleSubmit} className="auth-form">
          <label className="field-group">
            <span className="field-label">Email</span>
            <input className="text-input" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field-group">
            <span className="field-label">Password</span>
            <input className="text-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="submit" className="primary-button">Log in</button>
        </form>
        {error && <div className="notice error" role="alert">{error}</div>}
        {error === "Email not confirmed" && (
          <button type="button" className="secondary-button" onClick={() => void resendConfirmation()}>
            Resend confirmation email
          </button>
        )}
        {message && <div className="notice success" role="status">{message}</div>}
        <p className="auth-switch">
          New to PortfolioPilot? <Link href="/register">Create an account</Link>
        </p>
      </div>
    </main>
  );
}
