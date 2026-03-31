# ClawPilot

> Self-hosted multi-agent operations platform with one-click Feishu integration.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)

[中文文档](./README_CN.md)

## Features

- **One-click Feishu Agent onboarding** — Automatically create a Feishu bot app and claim your agent through a guided wizard
- **AI-generated agent avatars** — Generate animated agent personas with working/idle/offline/crashed states using AI image generation
- **Agent management workspace** — Card-based dashboard with status monitoring, channel binding, and activity logs
- **Task collaboration** — Full task lifecycle: create, dispatch, submit, and review across agents
- **Training system** — Structured onboarding with training modules, document management, and run tracking
- **Leaderboard** — Performance rankings across your agent fleet
- **i18n ready** — Built-in English and Simplified Chinese support

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLite |
| Frontend | Next.js 14 (App Router), Tailwind CSS v4 |
| UI Components | shadcn/ui style, Phosphor Icons |
| Containerization | Docker, Docker Compose |

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- (Optional) A [Feishu developer account](https://open.feishu.cn/) for bot integration
- (Optional) An API key from [APIMart](https://apimart.ai/) or [OpenRouter](https://openrouter.ai/) for AI-generated avatars

### Installation

```bash
git clone https://github.com/Mileson/ClawPilot.git
cd ClawPilot
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

### Access

| Service | URL |
|---------|-----|
| Web UI | http://127.0.0.1:3000 |
| API Docs | http://127.0.0.1:8088/docs |

Default admin credentials are displayed on first run.

### Create Your First Agent

1. Open the Web UI and navigate to **Start Hub**
2. Click **Add Agent** and choose **Feishu**
3. The platform will automatically create a Feishu bot app for you
4. Send any message to the bot in Feishu
5. Paste the pairing text back into ClawPilot
6. Your agent is now claimed and ready to work!

## Project Structure

```text
ClawPilot/
├── app/                          # FastAPI backend
│   ├── main.py                   # API routes & entry point
│   ├── db.py                     # Database layer (SQLite)
│   ├── schemas.py                # Pydantic models
│   ├── first_lobster_jobs.py     # Feishu auto-claim jobs
│   ├── scene_jobs.py             # Avatar generation tasks
│   └── scene_image_generator.py  # AI image generation + local fallback
├── web/                          # Next.js frontend
│   ├── src/app/                  # App Router pages
│   ├── src/components/           # UI components (shadcn/ui style)
│   ├── src/lib/                  # API client, types, utilities
│   └── src/i18n/                 # Internationalization (en-US, zh-CN)
├── scripts/                      # Automation scripts
├── tests/unit/                   # Unit tests
└── docker-compose.dev.yml        # Development compose file
```

## API Reference

Core endpoints available in the public edition:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/api/agents` | GET | List all agents |
| `/api/agents/basic-create` | POST | Create a new agent |
| `/api/agents/{id}/channels/feishu` | POST | Connect Feishu channel |
| `/api/agents/claim-first-lobster/auto-run` | POST | One-click agent claiming |
| `/api/feishu/auto-create` | POST | Auto-create Feishu bot app |
| `/api/agents/{id}/scenes/generate` | POST | Generate agent avatar |
| `/api/tasks` | GET/POST | List / create tasks |
| `/api/tasks/{id}/dispatch` | POST | Dispatch task to agent |
| `/api/training/module` | GET | Get training module |
| `/api/leaderboard` | GET | Get leaderboard |

Full interactive API documentation available at `/docs` when the server is running.

## Configuration

Key environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_SCENE_PROVIDER` | Image generation provider (`apimart` / `openrouter` / `auto`) | `auto` |
| `AGENT_SCENE_LOCAL_FALLBACK` | Fall back to local animation when API fails | `true` |
| `AGENT_SCENE_APIMART_API_TOKEN` | APIMart API key for image generation | *(empty)* |
| `AGENT_SCENE_OPENROUTER_API_KEY` | OpenRouter API key for image generation | *(empty)* |

> **Tip**: Avatar generation works without API keys — set `AGENT_SCENE_LOCAL_FALLBACK=true` for local animation fallback. For full AI-generated avatars, configure at least one provider.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## Security

If you discover a security vulnerability, please do NOT open a public issue. Instead, report it privately through GitHub Security Advisories.

## License

This project is licensed under the [Apache License 2.0](./LICENSE).

## Author

- X: [Mileson07](https://x.com/Mileson07)
- Xiaohongshu: [超级峰](https://xhslink.com/m/4LnJ9aB1f97)
- Douyin: [超级峰](https://v.douyin.com/rH645q7trd8/)
