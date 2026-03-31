import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isStartHubCompletionValue, START_HUB_COMPLETION_COOKIE } from "@/lib/start-hub-completion";

export default async function HomePage() {
  const cookieStore = await cookies();
  const startHubCompleted = isStartHubCompletionValue(cookieStore.get(START_HUB_COMPLETION_COOKIE)?.value);
  redirect(startHubCompleted ? "/agents" : "/start");
}
