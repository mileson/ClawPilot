import { getAgents } from "@/lib/api";
import { AddAgentMainPathPage } from "@/components/control-plane/add-agent-main-path-page";

export const revalidate = 0;

export default async function AddAgentPage() {
  const agents = await getAgents();
  return <AddAgentMainPathPage agents={agents} />;
}
