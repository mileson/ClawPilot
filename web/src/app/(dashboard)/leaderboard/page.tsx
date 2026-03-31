import { LeaderboardPageContent } from "@/components/leaderboard/leaderboard-page";
import { getLeaderboard } from "@/lib/api";

export const revalidate = 0;

export default async function LeaderboardPage() {
  const rows = await getLeaderboard();

  return <LeaderboardPageContent rows={rows} />;
}
