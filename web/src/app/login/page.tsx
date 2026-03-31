"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getBootstrapAccount, loginAccount } from "@/lib/api";
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

function LoginPageContent() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootstrapInfo, setBootstrapInfo] = useState<{
    username: string;
    temp_password?: string | null;
    created_at?: string | null;
    revealed_at?: string | null;
  } | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);

  function formatRevealTime(raw?: string | null) {
    if (!raw) return null;
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  useEffect(() => {
    const token = getStoredSessionToken();
    const next = resolvePostAuthPath(searchParams.get("next"));
    if (token) {
      if (getStoredAccountMeta()?.must_change_password) {
        router.replace(buildAuthRedirectPath("/account/password", next));
        return;
      }
      router.replace(next);
    }
  }, [router, searchParams]);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await loginAccount({ username, password });
      window.localStorage.setItem("oc_session", result.token);
      setStoredAccountMeta(result.account);
      const next = resolvePostAuthPath(searchParams.get("next"));
      if (result.account.must_change_password) {
        router.replace(buildAuthRedirectPath("/account/password", next));
        return;
      }
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.errors.loginFailed"));
    } finally {
      setLoading(false);
    }
  }

  async function handleRevealBootstrap() {
    setBootstrapLoading(true);
    setError(null);
    try {
      const info = await getBootstrapAccount();
      setBootstrapInfo(info);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.errors.bootstrapFailed"));
    } finally {
      setBootstrapLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-6 py-12">
      <div className="w-full max-w-md space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t("login.title")}</CardTitle>
            <CardDescription>{t("login.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              <label className="grid gap-2 text-sm">
                <span>{t("login.form.username")}</span>
                <input
                  className="rounded-xl border border-[var(--line)] px-3 py-2"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label className="grid gap-2 text-sm">
                <span>{t("login.form.password")}</span>
                <input
                  className="rounded-xl border border-[var(--line)] px-3 py-2"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              {error ? <p className="text-sm text-red-600">{error}</p> : null}
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? t("login.actions.loggingIn") : t("login.actions.login")}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("login.bootstrap.title")}</CardTitle>
            <CardDescription>{t("login.bootstrap.description")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {bootstrapInfo?.temp_password ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                {t("login.bootstrap.revealed", {
                  username: bootstrapInfo.username,
                  password: bootstrapInfo.temp_password,
                })}
              </div>
            ) : bootstrapInfo ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {t("login.bootstrap.alreadyRevealed", {
                  username: bootstrapInfo.username,
                  revealedAt: formatRevealTime(bootstrapInfo.revealed_at) || t("login.bootstrap.unknownTime"),
                })}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">{t("login.bootstrap.hint")}</p>
            )}
            <Button variant="outline" onClick={handleRevealBootstrap} disabled={bootstrapLoading}>
              {bootstrapLoading ? t("login.bootstrap.loading") : t("login.bootstrap.action")}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--background)]" />}>
      <LoginPageContent />
    </Suspense>
  );
}
