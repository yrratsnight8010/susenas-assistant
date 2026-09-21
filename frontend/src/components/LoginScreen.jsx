import { useState } from "react";
import { apiFetch } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import Button from "./ui/Button.jsx";
import { Field, inputClass } from "./ui/Field.jsx";
import { FormError } from "./ui/Notice.jsx";

export default function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const result = await apiFetch("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: username.trim(), password }),
      });
      login(result.access_token, result.username, result.role);
    } catch (err) {
      setError(err.message || "Username atau password salah.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas bg-[image:radial-gradient(circle_at_15%_8%,rgba(30,41,59,0.05),transparent_45%),radial-gradient(circle_at_85%_94%,rgba(249,115,22,0.06),transparent_42%)] p-[clamp(16px,5vw,32px)]">
      <div className="w-full max-w-[400px] rounded-lg border border-line bg-surface px-[clamp(20px,5vw,34px)] pt-[clamp(24px,5vw,36px)] pb-[30px] shadow-md max-[480px]:px-[18px] max-[480px]:pt-6 max-[480px]:pb-[22px]">
        <div className="mb-7 text-left">
          <div className="font-mono text-[11.5px] tracking-[0.06em] text-action uppercase">
            Statistik &middot; RAG &middot; BPS
          </div>
          <h1 className="mt-2 mb-1.5 font-display text-[clamp(23px,4vw,27px)] leading-tight font-bold text-ink">
            Susenas Maret 2025
          </h1>
          <p className="mt-3.5 text-[14px] leading-normal text-ink-soft">
            Asisten tanya-jawab data Susenas, dengan sumber yang selalu tertelusuri.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <Field label="Username" htmlFor="login-username">
            <input
              type="text"
              id="login-username"
              className={inputClass}
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </Field>

          <Field label="Password" htmlFor="login-password">
            <input
              type="password"
              id="login-password"
              className={inputClass}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          <Button type="submit" variant="action" block className="mt-1.5" disabled={submitting}>
            {submitting ? "Memproses..." : "Masuk"}
          </Button>

          {error && <FormError>{error}</FormError>}
        </form>
      </div>
    </div>
  );
}
