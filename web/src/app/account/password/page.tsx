"use client";

import { Suspense, useEffect, useState, useSyncExternalStore } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { EyeIcon, EyeSlashIcon } from "@phosphor-icons/react";
import { ApiError, changePassword } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/components/i18n/use-locale";
import {
  buildAuthRedirectPath,
  getStoredAccountMeta,
  getStoredSessionToken,
  resolvePostAuthPath,
  setStoredAccountMeta,
} from "@/lib/auth-session";

function subscribeStoredAccountMeta(callback: () => void) {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => callback();
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

type PasswordFieldProps = {
  label: string;
  value: string;
  visible: boolean;
  required?: boolean;
  minLength?: number;
  onChange: (value: string) => void;
  onToggle: () => void;
  toggleLabel: string;
};

function PasswordField({
  label,
  value,
  visible,
  required,
  minLength,
  onChange,
  onToggle,
  toggleLabel,
}: PasswordFieldProps) {
  return (
    <label className="grid gap-2 text-sm">
      <span>{label}</span>
      <span className="relative">
        <input
          className="w-full rounded-xl border border-[var(--line)] px-3 py-2 pr-11"
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          minLength={minLength}
          required={required}
        />
        <button
          type="button"
          onClick={onToggle}
          aria-label={toggleLabel}
          title={toggleLabel}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-[var(--muted-foreground)] transition hover:text-[var(--foreground)]"
        >
          {visible ? <EyeSlashIcon size={18} /> : <EyeIcon size={18} />}
        </button>
      </span>
    </label>
  );
}

function ChangePasswordPageContent() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mustChangePassword = useSyncExternalStore(
    subscribeStoredAccountMeta,
    () => Boolean(getStoredAccountMeta()?.must_change_password),
    () => false,
  );
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getStoredSessionToken();
    if (!token) {
      router.replace(buildAuthRedirectPath("/login", resolvePostAuthPath(searchParams.get("next"))));
    }
  }, [router, searchParams]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    const normalizedCurrentPassword = currentPassword.trim();
    if (!mustChangePassword && !normalizedCurrentPassword) {
      setError(t("password.errors.currentRequired"));
      return;
    }
    if (!newPassword || newPassword !== confirmPassword) {
      setError(t("password.errors.mismatch"));
      return;
    }
    if (newPassword.length < 10) {
      setError(t("password.errors.minLength", { min: 10 }));
      return;
    }
    setLoading(true);
    try {
      const account = await changePassword({
        current_password: normalizedCurrentPassword || undefined,
        new_password: newPassword,
      });
      setStoredAccountMeta(account);
      setSuccess(t("password.notices.updated"));
      const next = resolvePostAuthPath(searchParams.get("next"));
      setTimeout(() => {
        router.replace(next);
      }, 800);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.message === "account_password_invalid") {
          setError(t("password.errors.currentInvalid"));
        } else if (err.message === "account_password_required") {
          setError(t("password.errors.currentRequired"));
        } else {
          setError(err.message);
        }
      } else {
        setError(err instanceof Error ? err.message : t("password.errors.updateFailed"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-6 py-12">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t("password.title")}</CardTitle>
          <CardDescription>{t("password.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {!mustChangePassword ? (
              <PasswordField
                label={t("password.form.current")}
                value={currentPassword}
                visible={showCurrentPassword}
                onChange={setCurrentPassword}
                onToggle={() => setShowCurrentPassword((value) => !value)}
                toggleLabel={showCurrentPassword ? t("password.actions.hidePassword") : t("password.actions.showPassword")}
              />
            ) : null}
            <PasswordField
              label={t("password.form.new")}
              value={newPassword}
              visible={showNewPassword}
              onChange={setNewPassword}
              onToggle={() => setShowNewPassword((value) => !value)}
              toggleLabel={showNewPassword ? t("password.actions.hidePassword") : t("password.actions.showPassword")}
              minLength={10}
              required
            />
            <PasswordField
              label={t("password.form.confirm")}
              value={confirmPassword}
              visible={showConfirmPassword}
              onChange={setConfirmPassword}
              onToggle={() => setShowConfirmPassword((value) => !value)}
              toggleLabel={showConfirmPassword ? t("password.actions.hidePassword") : t("password.actions.showPassword")}
              required
            />
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {success ? <p className="text-sm text-emerald-600">{success}</p> : null}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? t("password.actions.submitting") : t("password.actions.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default function ChangePasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--background)]" />}>
      <ChangePasswordPageContent />
    </Suspense>
  );
}
