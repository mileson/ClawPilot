import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getAgents, getNodes, getSetupStatus } from "@/lib/api";
import { StartHubPage } from "@/components/control-plane/start-hub-page";
import { isStartHubCompletionValue, START_HUB_COMPLETION_COOKIE } from "@/lib/start-hub-completion";

export const revalidate = 0;

export default async function StartPage() {
  const cookieStore = await cookies();
  const startHubCompleted = isStartHubCompletionValue(cookieStore.get(START_HUB_COMPLETION_COOKIE)?.value);
  if (startHubCompleted) {
    redirect("/agents");
  }
  const [setup, nodes, agents] = await Promise.all([getSetupStatus(), getNodes(), getAgents()]);
  return <StartHubPage setup={setup} nodes={nodes.items} agents={agents} />;
}
