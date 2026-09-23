"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

type Step = "form" | "loading" | "success" | "invalid";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("loading");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Supabase embeds the session tokens in the URL hash after redirect.
    // getSession() picks them up automatically.
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        setStep("form");
      } else {
        setStep("invalid");
      }
    });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!/[A-Z]/.test(password)) {
      setError("Password must contain at least one uppercase letter.");
      return;
    }
    if (!/[0-9]/.test(password)) {
      setError("Password must contain at least one digit.");
      return;
    }

    setIsSubmitting(true);
    try {
      const supabase = createClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        setError(updateError.message);
      } else {
        setStep("success");
        setTimeout(() => router.replace("/login"), 2500);
      }
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <span className="text-2xl font-bold text-primary-700">SkillMesh</span>
          </Link>
          <p className="mt-2 text-slate-500 text-sm">Set a new password</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
          {/* Loading */}
          {step === "loading" && (
            <div className="text-center py-8">
              <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-sm text-slate-500">Verifying reset link…</p>
            </div>
          )}

          {/* Invalid / expired link */}
          {step === "invalid" && (
            <div className="text-center">
              <div className="text-4xl mb-4">⚠️</div>
              <h2 className="text-lg font-bold text-slate-900 mb-2">
                Link expired or invalid
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                This password reset link has expired or is invalid. Please
                request a new one.
              </p>
              <Link
                href="/forgot-password"
                className="inline-block text-sm font-semibold bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 transition"
              >
                Request new link
              </Link>
            </div>
          )}

          {/* Success */}
          {step === "success" && (
            <div className="text-center">
              <div className="text-4xl mb-4">✅</div>
              <h2 className="text-lg font-bold text-slate-900 mb-2">
                Password updated
              </h2>
              <p className="text-sm text-slate-500">
                Your password has been changed successfully. Redirecting you to
                sign in…
              </p>
            </div>
          )}

          {/* Form */}
          {step === "form" && (
            <>
              <h2 className="text-lg font-bold text-slate-900 mb-1">
                Choose a new password
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                At least 8 characters, one uppercase letter, one digit.
              </p>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 mb-4">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    New password
                  </label>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 transition"
                    placeholder="••••••••"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    Confirm new password
                  </label>
                  <input
                    type="password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 transition"
                    placeholder="••••••••"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
                >
                  {isSubmitting ? "Updating…" : "Update password"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
