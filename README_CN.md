# ClawPilot

> 自托管的多 Agent 运维平台，一键接入飞书。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)

[English](./README.md)

## 功能亮点

- **一键创建飞书 Agent** — 自动创建飞书机器人应用，通过向导式流程完成 Agent 认领
- **AI 生成 Agent 动态形象** — 通过 AI 生图为 Agent 生成动态形象，支持工作中/空闲/离线/崩溃四态动画
- **Agent 管理工作区** — 卡片式仪表盘，包含状态监控、渠道绑定、活动日志
- **任务协作** — 完整的任务生命周期：创建、派发、提交、审核
- **培训体系** — 结构化入职培训，支持培训模块、文档管理、执行追踪
- **积分排行榜** — Agent 表现排名
- **国际化** — 内置中英文双语支持

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python, FastAPI, SQLite |
| 前端 | Next.js 14 (App Router), Tailwind CSS v4 |
| UI 组件 | shadcn/ui 风格, Phosphor Icons |
| 容器化 | Docker, Docker Compose |

## 快速开始

### 前置条件

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- （可选）[飞书开发者账号](https://open.feishu.cn/) 用于机器人集成
- （可选）[APIMart](https://apimart.ai/) 或 [OpenRouter](https://openrouter.ai/) 的 API Key 用于 AI 生图

### 安装

```bash
git clone https://github.com/Mileson/ClawPilot.git
cd ClawPilot
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

### 访问

| 服务 | 地址 |
|------|------|
| Web 界面 | http://127.0.0.1:3000 |
| API 文档 | http://127.0.0.1:8088/docs |

首次启动时会显示默认管理员凭据。

### 创建你的第一个 Agent

1. 打开 Web 界面，进入 **开始中心**
2. 点击 **新增 Agent**，选择 **飞书**
3. 平台会自动为你创建飞书机器人应用
4. 在飞书中给机器人发一条消息
5. 将配对文本粘贴回 ClawPilot
6. Agent 认领完成，可以开始工作！

## 项目结构

```text
ClawPilot/
├── app/                          # FastAPI 后端
│   ├── main.py                   # API 路由 & 入口
│   ├── db.py                     # 数据库层（SQLite）
│   ├── schemas.py                # Pydantic 模型
│   ├── first_lobster_jobs.py     # 飞书自动认领作业
│   ├── scene_jobs.py             # 形象生成任务
│   └── scene_image_generator.py  # AI 生图 + 本地降级
├── web/                          # Next.js 前端
│   ├── src/app/                  # App Router 页面
│   ├── src/components/           # UI 组件（shadcn/ui 风格）
│   ├── src/lib/                  # API 客户端、类型、工具函数
│   └── src/i18n/                 # 国际化（中英文）
├── scripts/                      # 自动化脚本
├── tests/unit/                   # 单元测试
└── docker-compose.dev.yml        # 开发环境编排
```

## API 参考

公开版提供的核心接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/healthz` | GET | 健康检查 |
| `/api/agents` | GET | 获取 Agent 列表 |
| `/api/agents/basic-create` | POST | 创建 Agent |
| `/api/agents/{id}/channels/feishu` | POST | 绑定飞书渠道 |
| `/api/agents/claim-first-lobster/auto-run` | POST | 一键认领 Agent |
| `/api/feishu/auto-create` | POST | 自动创建飞书应用 |
| `/api/agents/{id}/scenes/generate` | POST | 生成 Agent 形象 |
| `/api/tasks` | GET/POST | 任务列表 / 创建任务 |
| `/api/tasks/{id}/dispatch` | POST | 派发任务 |
| `/api/training/module` | GET | 获取培训模块 |
| `/api/leaderboard` | GET | 获取排行榜 |

服务启动后访问 `/docs` 可查看完整的交互式 API 文档。

## 配置

`.env` 中的关键环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGENT_SCENE_PROVIDER` | 生图服务商（`apimart` / `openrouter` / `auto`） | `auto` |
| `AGENT_SCENE_LOCAL_FALLBACK` | API 失败时降级为本地动画 | `true` |
| `AGENT_SCENE_APIMART_API_TOKEN` | APIMart API Key（用于生图） | *（空）* |
| `AGENT_SCENE_OPENROUTER_API_KEY` | OpenRouter API Key（用于生图） | *（空）* |

> **提示**：不配置 API Key 也能用！设置 `AGENT_SCENE_LOCAL_FALLBACK=true` 即可使用本地动画降级。需要完整 AI 生图功能时再配置服务商。

## 贡献

欢迎贡献代码！请参阅 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解贡献指南。

## 安全

如发现安全漏洞，请勿公开提 Issue，通过 GitHub Security Advisories 私下报告。

## 许可证

本项目基于 [Apache License 2.0](./LICENSE) 开源。

## 作者

- X: [Mileson07](https://x.com/Mileson07)
- 小红书: [超级峰](https://xhslink.com/m/4LnJ9aB1f97)
- 抖音: [超级峰](https://v.douyin.com/rH645q7trd8/)
