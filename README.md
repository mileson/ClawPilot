# CJFClawPilot

**Self-hosted multi-agent operations platform with Feishu integration.**

CJFClawPilot helps you create, manage, and coordinate AI agents through Feishu (Lark). One-click Feishu app creation, automatic pairing, AI-generated agent avatars, and task management out of the box.

## Highlights

- **One-click Feishu Agent onboarding** — Automatically create a Feishu bot app and claim your agent in seconds
- **AI-generated agent avatars** — Generate animated agent personas with working/idle/offline/crashed states
- **Agent management workspace** — Card-based agent dashboard with status, channels, and activity logs
- **Task collaboration** — Create, dispatch, submit, and review tasks across agents
- **Training system** — Structured onboarding with training modules and run tracking
- **Leaderboard** — Performance rankings across your agent fleet

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) A Feishu developer account for bot integration
- (Optional) An API key for AI image generation (APIMart or OpenRouter)

### 1. Clone & Configure

```bash
git clone https://github.com/Mileson/CJFClawPilot.git
cd CJFClawPilot
cp .env.example .env
```

### 2. Launch

```bash
docker compose -f docker-compose.dev.yml up --build
```

### 3. Access

- **Web UI**: http://127.0.0.1:3000
- **API Docs**: http://127.0.0.1:8088/docs

Default admin credentials are shown on first `bootstrap` run.

### 4. Create Your First Agent

1. Open the Web UI and go to **Start Hub**
2. Click **Add Agent** → Choose **Feishu**
3. The platform will automatically create a Feishu bot app for you
4. Send any message to the bot in Feishu
5. Paste the pairing text back in CJFClawPilot
6. Your agent is now claimed and ready!

## Architecture

```text
Browser (Next.js UI)
       |
       v
 Next.js (web:3000)
 - shadcn/ui components
 - Phosphor icons
 - /api/* rewrite
       |
       v
 FastAPI (api:8088)
       |
       v
    SQLite DB
```

## Environment Variables

Key variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_SCENE_PROVIDER` | Image generation provider (`apimart` / `openrouter` / `auto`) | `auto` |
| `AGENT_SCENE_LOCAL_FALLBACK` | Fall back to local animation when API fails | `false` |
| `AGENT_SCENE_APIMART_API_TOKEN` | APIMart API key for image generation | (empty) |
| `AGENT_SCENE_OPENROUTER_API_KEY` | OpenRouter API key for image generation | (empty) |
| `FEISHU_USER_AUTH_AGENT_IDS` | Agent IDs allowed for user auth | `hr` |

> **Note**: Scene avatar generation works without API keys if `AGENT_SCENE_LOCAL_FALLBACK=true`. For full AI-generated avatars, configure at least one provider.

## Core API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/api/agents` | GET | List all agents |
| `/api/agents/basic-create` | POST | Create a new agent |
| `/api/agents/{id}/channels/feishu` | POST | Connect Feishu channel |
| `/api/agents/claim-first-lobster/auto-run` | POST | One-click claim agent |
| `/api/feishu/auto-create` | POST | Auto-create Feishu bot app |
| `/api/agents/{id}/scenes/generate` | POST | Generate agent avatar |
| `/api/tasks` | GET/POST | List / create tasks |
| `/api/training/module` | GET | Get training module |
| `/api/leaderboard` | GET | Get leaderboard |

Full API documentation available at `/docs` when the server is running.

## Tech Stack

- **Backend**: Python + FastAPI + SQLite
- **Frontend**: Next.js 14 (App Router) + Tailwind CSS v4 + shadcn/ui
- **Icons**: Phosphor Icons (`@phosphor-icons/react`)
- **Containerization**: Docker + Docker Compose

## License

This project is licensed under the **Business Source License 1.1** (BUSL-1.1).

- You may use, modify, and deploy this software for non-production purposes.
- Production use requires a commercial license — see [LICENSE](./LICENSE) for details.
- After the change date, the code will convert to GPL v2.0 or later.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.
