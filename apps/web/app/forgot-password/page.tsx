"use client";

import { useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

type Step = "form" | "sent" | "error";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [step, setStep] = useState<Step>("form");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage("");

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });

      if (error) {
        setErrorMessage(error.message);
        setStep("error");
      } else {
        setStep("sent");
      }
    } catch {
      setErrorMessage("Something went wrong. Please try again.");
      setStep("error");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <span className="text-2xl font-bold text-primary-700">SkillMesh</span>
          </Link>
          <p className="mt-2 text-slate-500 text-sm">Reset your password</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
          {/* ── Sent state ── */}
          {step === "sent" && (
            <div className="text-center">
              <div className="text-4xl mb-4">📧</div>
              <h2 className="text-lg font-bold text-slate-900 mb-2">
                Check your email
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                We sent a password reset link to{" "}
                <span className="font-medium text-slate-700">{email}</span>.
                Check your inbox and click the link to reset your password.
              </p>
              <p className="text-xs text-slate-400 mb-6">
                Didn't receive it? Check your spam folder, or{" "}
                <button
                  onClick={() => setStep("form")}
                  className="text-primary-600 hover:text-primary-700 underline"
                >
                  try again
                </button>
                .
              </p>
              <Link
                href="/login"
                className="inline-block text-sm font-semibold text-primary-600 hover:text-primary-700"
              >
                ← Back to sign in
              </Link>
            </div>
          )}

          {/* ── Form state ── */}
          {(step === "form" || step === "error") && (
            <>
              <h2 className="text-lg font-bold text-slate-900 mb-1">
                Forgot your password?
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                Enter the email address associated with your account and we'll
                send you a link to reset your password.
              </p>

              {step === "error" && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 mb-4">
                  {errorMessage || "Failed to send reset email. Please try again."}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-slate-700 mb-1.5"
                  >
                    Email address
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition"
                    placeholder="you@institution.edu"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
                >
                  {isSubmitting ? "Sending…" : "Send reset link"}
                </button>
              </form>

              <p className="mt-6 text-center text-sm text-slate-500">
                Remember your password?{" "}
                <Link
                  href="/login"
                  className="font-medium text-primary-600 hover:text-primary-700"
                >
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
