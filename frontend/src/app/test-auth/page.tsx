"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function TestAuthPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<string>("");

  const supabase = createClient();

  async function handleLogin() {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setResult(`Login error: ${error.message}`);
      return;
    }
    setResult(`Logged in. User id: ${data.user?.id}`);
  }

  async function handleSignup() {
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) {
    setResult(`Signup error: ${error.message}`);
    return;
  }
  if (data.session) {
    setResult(`Signed up and logged in. User id: ${data.user?.id}`);
  } else {
    setResult(`Signed up. Check email to confirm before logging in.`);
  }
}


  async function handleCallMe() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      setResult("No active session — log in first.");
      return;
    }

    const res = await fetch("http://127.0.0.1:8000/users/me", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    const body = await res.json();
    setResult(`Status ${res.status}: ${JSON.stringify(body)}`);
  }

  async function handleLogout() {
    await supabase.auth.signOut();
    setResult("Logged out.");
  }

  return (
    <div style={{ padding: 40 }}>
      <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button onClick={handleLogin}>Log in</button>
      <button onClick={handleCallMe}>Call /users/me</button>
      <button onClick={handleLogout}>Log out</button>
      <button onClick={handleSignup}>Sign up</button>

      <pre>{result}</pre>
    </div>
  );
}
