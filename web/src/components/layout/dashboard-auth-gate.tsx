"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { useI18n } from "@/components/i18n/use-locale";
import {
  buildAuthRedirectPath,
  buildNextPath,
  getStoredAccountMeta,
  getStoredSessionToken,
} from "@/lib/auth-session";

export function DashboardAuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { t } = useI18n();
  const [hydrated, setHydrated] = useState(false);
  const token = hydrated ? getStoredSessionToken() : null;
  const mustChangePassword = hydrated ? Boolean(getStoredAccountMeta()?.must_change_password) : false;
  const authorized = hydrated && Boolean(token) && !mustChangePassword;

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const nextPath = buildNextPath(pathname, searchParams);

    if (!token) {
      router.replace(buildAuthRedirectPath("/login", nextPath));
    } else if (mustChangePassword) {
      router.replace(buildAuthRedirectPath("/account/password", nextPath));
    }
  }, [hydrated, router, pathname, searchParams, token, mustChangePassword]);

  if (!hydrated || !authorized) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-6 py-12">
        <div
          className="relative flex h-36 w-36 items-center justify-center rounded-full border border-white/70 bg-white/75 shadow-[0_24px_64px_rgba(15,23,42,0.08)] backdrop-blur-sm"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle,rgba(18,18,18,0.08),transparent_70%)] animate-pulse" />
          <div className="relative flex h-20 w-20 items-center justify-center overflow-hidden rounded-full bg-white shadow-[0_12px_24px_rgba(18,18,18,0.10)]">
            <Image
              src="/branding/clawpilot-sidebar.png"
              alt=""
              aria-hidden="true"
              width={80}
              height={80}
              className="h-full w-full scale-[1.06] object-cover motion-safe:animate-[spin_3.2s_linear_infinite]"
              priority
            />
          </div>
          <span className="sr-only">{t("authGate.checking")}</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
