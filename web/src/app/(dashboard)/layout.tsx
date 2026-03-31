import { cookies } from "next/headers";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { DashboardAuthGate } from "@/components/layout/dashboard-auth-gate";
import { isStartHubCompletionValue, START_HUB_COMPLETION_COOKIE } from "@/lib/start-hub-completion";

export const revalidate = 0;
export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const startHubCompleted = isStartHubCompletionValue(cookieStore.get(START_HUB_COMPLETION_COOKIE)?.value);

  return (
    <DashboardAuthGate>
      <DashboardShell startHubCompleted={startHubCompleted}>{children}</DashboardShell>
    </DashboardAuthGate>
  );
}
