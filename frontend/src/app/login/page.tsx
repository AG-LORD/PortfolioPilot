"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const router = useRouter();
  const supabase = createClient();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);

    if (mode === "register") {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) {
        setError(error.message);
        return;
      }
      if (data.session) {
        router.push("/dashboard");
      } else {
        setMessage("Check your email to confirm your account, then log in.");
      }
      return;
    }

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
    <div style={{ padding: 40, maxWidth: 440 }}>
      <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
      <p>{mode === "login" ? "Log in to manage your portfolios." : "Create an account to start building your portfolio."}</p>
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 16, padding: 24, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }}>
        <label>
          Email
          <input type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        </label>
        <button type="submit">{mode === "login" ? "Log in" : "Create account"}</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {mode === "login" && error === "Email not confirmed" && (
        <button type="button" onClick={() => void resendConfirmation()}>
          Resend confirmation email
        </button>
      )}
      {message && <p role="status">{message}</p>}
      <p>
        {mode === "login" ? "New to PortfolioPilot?" : "Already have an account?"}{" "}
        <button
          type="button"
          onClick={() => {
            setMode((currentMode) => currentMode === "login" ? "register" : "login");
            setError(null);
            setMessage(null);
          }}
          style={{ padding: 0, border: "none", background: "none", color: "var(--primary)", textDecoration: "underline" }}
        >
          {mode === "login" ? "Register" : "Log in"}
        </button>
      </p>
    </div>
  );
}
