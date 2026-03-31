import type { Agent } from "@/lib/types";
import type { Translator } from "@/i18n";

const CHANNEL_META: Record<
  string,
  {
    key: string;
    iconSrc?: string;
    monogram?: string;
  }
> = {
  feishu: {
    key: "common.platforms.feishu",
    iconSrc: "/platforms/feishu.png",
  },
  discord: {
    key: "common.platforms.discord",
    iconSrc: "/platforms/discord.svg",
  },
  telegram: {
    key: "common.platforms.telegram",
    iconSrc: "/platforms/telegram.svg",
  },
  weixin: {
    key: "common.platforms.weixin",
    iconSrc: "/platforms/wechat.svg",
  },
};

const AVATAR_HINT_EMOJI: Array<[RegExp, string]> = [
  [/天平/, "⚖️"],
  [/画笔|调色板/, "🎨"],
  [/文档/, "📄"],
  [/DNA|双螺旋|进化/, "🧬"],
  [/安全|盾/, "🛡️"],
  [/代码|工程/, "💻"],
  [/产品/, "📌"],
  [/项目|任务/, "📋"],
  [/教练|培训/, "🧑‍🏫"],
  [/法务|法律/, "⚖️"],
];

function hashColor(agentId: string): { bg: string; fg: string } {
  let hash = 0;
  for (let i = 0; i < agentId.length; i += 1) hash = (hash * 33 + agentId.charCodeAt(i)) >>> 0;
  const hue = hash % 360;
  return { bg: `hsl(${hue} 45% 88%)`, fg: `hsl(${hue} 45% 22%)` };
}

function pickEmoji(agent: Agent): string | null {
  const emoji = (agent.emoji || "").trim();
  if (emoji && !emoji.includes("待设置")) return emoji;

  const hint = (agent.avatar_hint || "").trim();
  for (const [pattern, symbol] of AVATAR_HINT_EMOJI) {
    if (pattern.test(hint)) return symbol;
  }
  return null;
}

function fallbackText(agent: Agent): string {
  const name = agent.display_name?.trim() || agent.agent_id;
  return name.slice(0, 1).toUpperCase();
}

export function avatarFromAgent(agent: Agent): string {
  const remoteAvatar = avatarReferenceFromAgent(agent);
  if (remoteAvatar) return remoteAvatar;

  const symbol = pickEmoji(agent) || fallbackText(agent);
  const { bg, fg } = hashColor(agent.agent_id);
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect width="96" height="96" rx="24" fill="${bg}" />
  <text x="50%" y="50%" dominant-baseline="central" text-anchor="middle"
        font-size="44" font-family="Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif"
        fill="${fg}">${symbol}</text>
</svg>`.trim();
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export function channelLabel(channel: string, t: Translator): string {
  return platformMeta(channel, t).label;
}

export function platformMeta(
  channel: string,
  t: Translator,
): { label: string; iconSrc?: string; monogram?: string } {
  const key = (channel || "").trim().toLowerCase();
  if (!key) {
    return {
      label: "待配置渠道",
      monogram: "待",
    };
  }
  if (CHANNEL_META[key]) {
    const meta = CHANNEL_META[key];
    const label = t(meta.key);
    return {
      label,
      iconSrc: meta.iconSrc,
      monogram: meta.monogram ?? label.slice(0, 1),
    };
  }

  const fallback = key ? key.toUpperCase() : t("common.platforms.unknown");
  return {
    label: fallback,
    monogram: fallback.slice(0, 1),
  };
}

export function avatarReferenceFromAgent(agent: Agent): string | null {
  if (agent.avatar_url && /^https?:\/\//.test(agent.avatar_url)) return agent.avatar_url;
  if (agent.avatar_hint && /^https?:\/\//.test(agent.avatar_hint)) return agent.avatar_hint;
  return null;
}

export function hasRealAvatar(agent: Agent): boolean {
  return Boolean(avatarReferenceFromAgent(agent));
}
