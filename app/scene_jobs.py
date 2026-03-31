# Copyright (c) 2026 ClawPilot Contributors. All rights reserved.
# Licensed under the Business Source License 1.1 — see LICENSE file.
# NOTICE: Reverse engineering, decompilation, or disassembly is prohibited.

import os
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db


class SceneJobDependencyError(RuntimeError):
    pass


def _scene_dependency_message(missing_module: str | None = None) -> str:
    suffix = f":{missing_module}" if missing_module else ""
    return (
        "scene_generator_dependency_missing"
        f"{suffix}"
        ":开发态默认未安装场景生图依赖，请使用 INSTALL_SCENE_TOOLS=1 重新执行 "
        "`docker compose -f docker-compose.dev.yml up --build`"
    )


def _load_scene_generator_module():
    try:
        from . import scene_image_generator
    except ModuleNotFoundError as exc:
        raise SceneJobDependencyError(_scene_dependency_message(exc.name)) from exc
    return scene_image_generator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SceneSpec:
    key: str
    label: str
    status_hint: str
    action_sequence: str


SCENE_SPECS: tuple[SceneSpec, ...] = (
    SceneSpec(
        key="working",
        label="正在干活",
        status_hint="当前有执行中的任务",
        action_sequence=(
            "1开始敲键盘，2持续输入，3看向右屏，4右手点按，5左手记录，6回到键盘，"
            "7加速输入，8检查输出，9前倾专注，10微调屏幕，11点头确认，12回到稳定工作姿态。"
        ),
    ),
    SceneSpec(
        key="idle",
        label="躺平中",
        status_hint="当前无执行中的任务",
        action_sequence=(
            "1放松坐姿，2轻敲桌面，3端起杯子，4慢慢喝水，5放下杯子，6目光看屏幕，"
            "7轻微后仰，8深呼吸，9转回键盘，10手放键盘待命，11短暂停顿，12保持待命姿态。"
        ),
    ),
    SceneSpec(
        key="offline",
        label="离线摸鱼",
        status_hint="离线不可达",
        action_sequence=(
            "1闭眼坐着，2轻微低头，3呼吸起伏，4头部小幅摆动，5短暂打盹，6肩膀放松，"
            "7继续闭眼，8手臂不动，9轻微抬头，10再次闭眼，11保持静止，12停在离线休眠姿态。"
        ),
    ),
    SceneSpec(
        key="crashed",
        label="崩溃中",
        status_hint="运行报错",
        action_sequence=(
            "1快速输入，2突然停下，3看向屏幕，4抬手排查，5紧张操作，6再次尝试，"
            "7出现故障反应，8继续排查，9记录问题，10重试失败，11深呼吸调整，12停在待修复姿态。"
        ),
    ),
)

DEFAULT_ASPECT_RATIO = os.getenv("AGENT_SCENE_ASPECT_RATIO", "21:9")
DEFAULT_RESOLUTION = os.getenv("AGENT_SCENE_RESOLUTION", "1K")
DEFAULT_FPS = os.getenv("AGENT_SCENE_FPS", "4")
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENE_ASSET_ROOT = Path("/data/scene-assets") if Path("/data").exists() else (REPO_ROOT / "data" / "scene-assets")
SCENE_ASSET_ROOT = Path(os.getenv("OPENCLAW_SCENE_ASSET_DIR", str(DEFAULT_SCENE_ASSET_ROOT)))

_JOBS: dict[str, dict[str, Any]] = {}
_RUNNING_JOB_BY_AGENT: dict[str, str] = {}
_LATEST_JOB_BY_AGENT: dict[str, str] = {}
_LOCK = threading.Lock()


def _scene_steps_template() -> list[dict[str, Any]]:
    return [
        {
            "scene": spec.key,
            "label": spec.label,
            "status": "pending",
            "message": None,
            "started_at": None,
            "finished_at": None,
            "output_mp4": None,
        }
        for spec in SCENE_SPECS
    ]


def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(job)


def _tail(text: str, limit: int = 1200) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[-limit:]


def _resolve_scene_dir(agent_id: str, scene_key: str) -> Path:
    return SCENE_ASSET_ROOT / "agents" / agent_id / scene_key


def _build_prompt(
    *,
    role_summary: str,
    scene_label: str,
    status_hint: str,
    action_sequence: str,
) -> str:
    return (
        "[硬性输出格式]\n"
        "必须输出一个4列x3行的分镜精灵图（共12格，12帧），阅读顺序严格为从左到右、从上到下。\n"
        "每一格都必须是独立完整画面，禁止跨格延展，禁止把同一个人物身体跨越到上下两格。\n"
        "用细的浅灰分隔线把12格明确分开（仅用于分镜，不是卡片边框）。\n\n"
        "[身份锁定]\n"
        "严格以参考头像为唯一角色标准。角色必须保持同一人：脸型、五官比例、发型发色、肤色、年龄感、服装主色全部一致。\n"
        "禁止替换角色、禁止新增角色、禁止像另一个人的变化。\n\n"
        "[镜头锁定]\n"
        "每一格都使用同一机位、同一透视、同一构图：人物在左侧工位，右侧双屏与桌面设备，浅色办公室隔间背景。\n"
        "每一格都要出现完整角色上半身与完整工位画面，不允许缺头、截断、越界。\n\n"
        "[岗位与状态]\n"
        f"岗位职责：{role_summary}\n"
        f"当前状态：{scene_label}，{status_hint}。\n\n"
        "[动作连续]\n"
        "12帧必须小步连续，形成自然动画，不可跨帧突变：\n"
        f"{action_sequence}\n\n"
        "[画风]\n"
        "简洁卡通办公插画风，线条干净，柔和配色，与参考图观感一致。\n\n"
        "[禁止项]\n"
        "禁止任何文字、数字、logo、水印、UI标签、对白气泡、二维码、签名。"
    )


def _ensure_paths() -> None:
    SCENE_ASSET_ROOT.mkdir(parents=True, exist_ok=True)


def _step_index(scene_key: str) -> int:
    for idx, spec in enumerate(SCENE_SPECS):
        if spec.key == scene_key:
            return idx
    raise RuntimeError(f"unknown_scene_key: {scene_key}")


def _set_job(job_id: str, patch: dict[str, Any]) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        job.update(patch)


def _set_step(job_id: str, scene_key: str, patch: dict[str, Any]) -> None:
    idx = _step_index(scene_key)
    with _LOCK:
        _JOBS[job_id]["steps"][idx].update(patch)


def _scene_stage_label(scene_label: str, phase: str, upstream_status: str | None) -> str:
    status = (upstream_status or "").strip().lower()
    if phase == "submitted":
        return f"{scene_label}: 已提交上游"
    if phase == "resume":
        return f"{scene_label}: 恢复轮询中"
    if status in {"pending", "queued", "submitted"}:
        return f"{scene_label}: 上游排队中"
    if status in {"processing", "running", "in_progress"}:
        return f"{scene_label}: 上游处理中"
    if status in {"completed", "succeeded", "success"}:
        return f"{scene_label}: 下载结果中"
    if status in {"failed", "error", "cancelled"}:
        return f"{scene_label}: 上游失败"
    return f"{scene_label}: 生图中"


def _make_status_hook(job_id: str, spec: SceneSpec):
    def _hook(event: dict[str, Any]) -> None:
        upstream_task_id = event.get("task_id")
        upstream_status = event.get("upstream_status")
        current_stage = _scene_stage_label(spec.label, str(event.get("phase") or ""), upstream_status if isinstance(upstream_status, str) else None)
        patch: dict[str, Any] = {
            "current_scene": spec.key,
            "current_stage": current_stage,
            "last_poll_at": now_iso(),
        }
        if isinstance(upstream_task_id, str) and upstream_task_id.strip():
            patch["upstream_task_id"] = upstream_task_id.strip()
        if isinstance(upstream_status, str) and upstream_status.strip():
            patch["upstream_status"] = upstream_status.strip()
        _set_job(job_id, patch)
        _set_step(
            job_id,
            spec.key,
            {
                "status": "running",
                "message": current_stage.replace(f"{spec.label}: ", "", 1),
            },
        )

    return _hook


def _generate_single_scene(
    *,
    job_id: str,
    agent_id: str,
    avatar_url: str,
    role_summary: str,
    spec: SceneSpec,
) -> str:
    scene_image_generator = _load_scene_generator_module()
    scene_dir = _resolve_scene_dir(agent_id, spec.key)
    scene_dir.mkdir(parents=True, exist_ok=True)

    spritesheet_path = scene_dir / f"{agent_id}-{spec.key}-spritesheet.png"
    mp4_path = scene_dir / f"{agent_id}-{spec.key}.mp4"
    frames_dir = scene_dir / "frames"
    metadata_path = scene_dir / f"{agent_id}-{spec.key}-meta.json"
    prompt_path = scene_dir / f"{agent_id}-{spec.key}-prompt.txt"

    prompt = _build_prompt(
        role_summary=role_summary,
        scene_label=spec.label,
        status_hint=spec.status_hint,
        action_sequence=spec.action_sequence,
    )
    prompt_path.write_text(prompt, encoding="utf-8")

    _set_job(
        job_id,
        {"current_scene": spec.key, "current_stage": f"{spec.label}: 生图中"},
    )
    _set_step(
        job_id,
        spec.key,
        {"status": "running", "message": "生图中", "started_at": now_iso()},
    )

    generation_engine = "unknown"
    try:
        result = scene_image_generator.generate_spritesheet(
            prompt=prompt,
            reference_image=avatar_url,
            output_path=spritesheet_path,
            aspect_ratio=DEFAULT_ASPECT_RATIO,
            resolution=DEFAULT_RESOLUTION,
            status_hook=_make_status_hook(job_id, spec),
        )
        generation_engine = (result or {}).get("engine", "unknown")
    except ModuleNotFoundError as exc:
        raise SceneJobDependencyError(_scene_dependency_message(exc.name)) from exc
    except Exception as exc:
        raise RuntimeError(f"{spec.label}生图失败：{_tail(str(exc), 800)}") from exc

    _set_job(
        job_id,
        {"current_scene": spec.key, "current_stage": f"{spec.label}: 裁剪与合成中"},
    )
    _set_step(job_id, spec.key, {"message": "裁剪与合并MP4中"})

    try:
        scene_image_generator.crop_and_build_mp4(
            input_path=spritesheet_path,
            output_mp4=mp4_path,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            cols=4,
            rows=3,
            target_width=1536,
            target_height=648,
            fps=int(DEFAULT_FPS),
        )
    except ModuleNotFoundError as exc:
        raise SceneJobDependencyError(_scene_dependency_message(exc.name)) from exc
    except Exception as exc:
        raise RuntimeError(f"{spec.label}裁剪失败：{_tail(str(exc), 800)}") from exc

    rel = f"/api/agents/{agent_id}/scenes/{spec.key}.mp4"
    _set_step(
        job_id,
        spec.key,
        {
            "status": "completed",
            "message": f"已完成（{generation_engine}）",
            "finished_at": now_iso(),
            "output_mp4": rel,
        },
    )
    return rel


def _run_job(job_id: str, agent_id: str, avatar_url: str, role_summary: str) -> None:
    _set_job(
        job_id,
        {"status": "running", "started_at": now_iso(), "current_stage": "初始化"},
    )
    done = 0
    total = len(SCENE_SPECS)
    try:
        _ensure_paths()
        for spec in SCENE_SPECS:
            _generate_single_scene(
                job_id=job_id,
                agent_id=agent_id,
                avatar_url=avatar_url,
                role_summary=role_summary,
                spec=spec,
            )
            done += 1
            _set_job(job_id, {"progress_done": done, "progress_total": total})
        _set_job(
            job_id,
            {
                "status": "completed",
                "current_stage": "全部完成",
                "finished_at": now_iso(),
                "current_scene": None,
                "upstream_status": "completed",
            },
        )
    except Exception as exc:
        message = str(exc)
        _set_job(
            job_id,
            {
                "status": "failed",
                "error_message": message,
                "current_stage": "执行失败",
                "finished_at": now_iso(),
                "upstream_status": _JOBS[job_id].get("upstream_status") or "failed",
            },
        )
        current_scene = _JOBS[job_id].get("current_scene")
        if current_scene:
            _set_step(
                job_id,
                current_scene,
                {
                    "status": "failed",
                    "message": message,
                    "finished_at": now_iso(),
                },
            )
    finally:
        with _LOCK:
            _RUNNING_JOB_BY_AGENT.pop(agent_id, None)


def start_scene_job(agent_id: str, force: bool = False) -> dict[str, Any]:
    agent = db.get_agent_by_id(agent_id)
    if not agent:
        raise LookupError("agent_not_found")

    avatar_url = (agent.get("avatar_url") or "").strip()
    if not avatar_url.startswith(("http://", "https://")):
        raise ValueError("avatar_missing")

    role_summary = str(agent.get("role_summary") or agent.get("role") or "待补充岗位职责")
    _load_scene_generator_module()

    with _LOCK:
        running = _RUNNING_JOB_BY_AGENT.get(agent_id)
        if running and not force:
            raise RuntimeError(f"scene_job_in_progress:{running}")

        job_id = f"scn_{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "agent_id": agent_id,
            "status": "queued",
            "current_scene": None,
            "current_stage": "排队中",
            "upstream_task_id": None,
            "upstream_status": None,
            "last_poll_at": None,
            "progress_done": 0,
            "progress_total": len(SCENE_SPECS),
            "error_message": None,
            "created_at": now_iso(),
            "started_at": None,
            "finished_at": None,
            "steps": _scene_steps_template(),
        }
        _JOBS[job_id] = job
        _RUNNING_JOB_BY_AGENT[agent_id] = job_id
        _LATEST_JOB_BY_AGENT[agent_id] = job_id

    thread = threading.Thread(
        target=_run_job,
        kwargs={
            "job_id": job_id,
            "agent_id": agent_id,
            "avatar_url": avatar_url,
            "role_summary": role_summary,
        },
        daemon=True,
    )
    thread.start()
    return _snapshot(job)


def get_scene_job(agent_id: str, job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise LookupError("scene_job_not_found")
        if job.get("agent_id") != agent_id:
            raise LookupError("scene_job_not_found")
        return _snapshot(job)


def get_running_scene_job_for_agent(agent_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job_id = _RUNNING_JOB_BY_AGENT.get(agent_id)
        if not job_id:
            return None
        job = _JOBS.get(job_id)
        if not job:
            return None
        return _snapshot(job)


def get_latest_scene_job(agent_id: str) -> dict[str, Any]:
    with _LOCK:
        running_job_id = _RUNNING_JOB_BY_AGENT.get(agent_id)
        if running_job_id:
            running_job = _JOBS.get(running_job_id)
            if running_job:
                return _snapshot(running_job)

        latest_job_id = _LATEST_JOB_BY_AGENT.get(agent_id)
        if not latest_job_id:
            raise LookupError("scene_job_not_found")
        latest_job = _JOBS.get(latest_job_id)
        if not latest_job or latest_job.get("agent_id") != agent_id:
            raise LookupError("scene_job_not_found")
        return _snapshot(latest_job)


def scene_mp4_path(agent_id: str, scene_key: str) -> Path:
    scene_dir = _resolve_scene_dir(agent_id, scene_key)
    return scene_dir / f"{agent_id}-{scene_key}.mp4"
