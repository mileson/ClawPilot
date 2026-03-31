# Copyright (c) 2026 ClawPilot Contributors. All rights reserved.
# Licensed under the Business Source License 1.1 — see LICENSE file.
# NOTICE: Reverse engineering, decompilation, or disassembly is prohibited.

import base64
import io
import json
import math
import os
import time
from pathlib import Path
from typing import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import imageio.v2 as imageio
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageOps


def _default_task_cache_path() -> Path:
    base = Path("/data") if Path("/data").exists() else (Path(__file__).resolve().parent.parent / "data")
    return base / "scene-task-cache.json"


TASK_CACHE_PATH = Path(os.getenv("AGENT_SCENE_TASK_CACHE_PATH", str(_default_task_cache_path())))
StatusHook = Callable[[dict[str, Any]], None]


def _compact_error_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "未知错误"
    lower = text.lower()
    if "quota exceeded" in lower or "exceeded your current quota" in lower:
        return "APIMart 配额已用尽，请等待额度恢复后重试"
    if "http_error:403:error code: 1010" in lower:
        return "APIMart 请求被上游风控拦截（403/1010）"
    if "openrouter_api_key_missing" in lower:
        return "未配置 OpenRouter 备用密钥"
    if "apimart_api_token_missing" in lower:
        return "未配置 APIMart 密钥"
    if "apimart_task_timeout" in lower:
        return "APIMart 任务仍在排队或处理中，请稍后继续轮询"
    if "apimart_submit_failed" in lower:
        return "APIMart 提交失败"
    if "apimart_task_failed" in lower:
        return "APIMart 任务执行失败"
    return text[:180]


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "clawpilot/scene-generator",
    }
    if headers:
        req_headers.update(headers)
    try:
        resp = requests.request(method=method, url=url, headers=req_headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"url_error:{exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"http_error:{resp.status_code}:{(resp.text or '').strip()[:500]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"invalid_json_response:{(resp.text or '').strip()[:500]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("invalid_json_response")
    return data


def _download_to_file(url: str, output_path: Path, timeout: int = 120) -> None:
    normalized_url = url.strip()
    if normalized_url.startswith("/f/"):
        file_base = os.getenv("AGENT_SCENE_APIMART_FILE_BASE_URL", "https://upload.apimart.ai").strip() or "https://upload.apimart.ai"
        normalized_url = urljoin(f"{file_base.rstrip('/')}/", normalized_url.lstrip("/"))
    try:
        resp = requests.get(
            normalized_url,
            timeout=timeout,
            headers={"User-Agent": "clawpilot/scene-generator"},
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"download_url_error:{exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"download_http_error:{resp.status_code}:{(resp.text or '').strip()[:500]}")
    content = resp.content
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)


def _load_image_source(reference_image: str) -> str:
    if reference_image.startswith("http://") or reference_image.startswith("https://"):
        return reference_image
    path = Path(reference_image)
    if not path.exists():
        raise RuntimeError(f"reference_image_not_found:{reference_image}")
    ext = path.suffix.lower()
    mime = "image/jpeg"
    if ext == ".png":
        mime = "image/png"
    elif ext == ".webp":
        mime = "image/webp"
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extract_apimart_image_url(task_data: dict[str, Any]) -> str | None:
    def first_candidate(value: Any) -> str | None:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return parts[0] if parts else None
        if isinstance(value, list):
            for item in value:
                candidate = first_candidate(item)
                if candidate:
                    return candidate
        return None

    payloads: list[dict[str, Any]] = [task_data]
    if isinstance(task_data.get("data"), dict):
        payloads.append(task_data["data"])

    for payload in payloads:
        choices = (payload.get("output", {}) or {}).get("choices", [])
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                candidate = first_candidate(choice.get("image_url"))
                if candidate:
                    return candidate

        result_images = (payload.get("result", {}) or {}).get("images", [])
        if isinstance(result_images, list):
            for image_row in result_images:
                if not isinstance(image_row, dict):
                    continue
                candidate = first_candidate(image_row.get("url"))
                if candidate:
                    return candidate
    return None


def _extract_apimart_status(task_data: dict[str, Any]) -> str:
    status = task_data.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip().lower()
    payload = task_data.get("data", {})
    if isinstance(payload, dict):
        inner = payload.get("status")
        if isinstance(inner, str) and inner.strip():
            return inner.strip().lower()
    return ""


def _extract_apimart_error(task_data: dict[str, Any]) -> str:
    for payload in (task_data, task_data.get("data", {})):
        if not isinstance(payload, dict):
            continue
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(err, str) and err.strip():
            return err.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return "unknown_error"


def _load_task_cache() -> dict[str, dict[str, Any]]:
    try:
        if not TASK_CACHE_PATH.exists():
            return {}
        data = json.loads(TASK_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_task_cache(cache: dict[str, dict[str, Any]]) -> None:
    TASK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _task_cache_key(output_path: Path) -> str:
    return str(output_path.resolve())


def _get_cached_task_id(output_path: Path) -> str | None:
    cache = _load_task_cache()
    item = cache.get(_task_cache_key(output_path), {})
    if not isinstance(item, dict):
        return None
    task_id = item.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()
    return None


def _set_cached_task_id(output_path: Path, task_id: str) -> None:
    cache = _load_task_cache()
    cache[_task_cache_key(output_path)] = {"task_id": task_id, "updated_at": int(time.time())}
    _save_task_cache(cache)


def _clear_cached_task_id(output_path: Path) -> None:
    cache = _load_task_cache()
    key = _task_cache_key(output_path)
    if key in cache:
        del cache[key]
        _save_task_cache(cache)


def _extract_openrouter_image(response_data: dict[str, Any]) -> str | None:
    choices = response_data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None
    message = (choices[0] or {}).get("message", {})
    images = message.get("images", [])
    if not isinstance(images, list):
        return None
    for row in images:
        if not isinstance(row, dict):
            continue
        image_url = row.get("image_url") or row.get("imageUrl") or {}
        if isinstance(image_url, dict):
            maybe = image_url.get("url")
            if isinstance(maybe, str) and maybe.strip():
                return maybe.strip()
        elif isinstance(image_url, str) and image_url.strip():
            return image_url.strip()
    return None


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _scene_palette_from_prompt(prompt: str) -> dict[str, tuple[int, int, int]]:
    text = prompt or ""
    if "崩溃中" in text:
        return {
            "top": (85, 45, 45),
            "bottom": (48, 27, 27),
            "accent": (229, 82, 82),
            "monitor": (54, 22, 22),
            "desk": (125, 82, 82),
        }
    if "离线摸鱼" in text:
        return {
            "top": (52, 58, 72),
            "bottom": (29, 35, 48),
            "accent": (142, 161, 182),
            "monitor": (20, 28, 40),
            "desk": (83, 94, 113),
        }
    if "躺平中" in text:
        return {
            "top": (178, 206, 232),
            "bottom": (112, 152, 189),
            "accent": (54, 124, 196),
            "monitor": (58, 91, 125),
            "desk": (136, 177, 212),
        }
    return {
        "top": (164, 226, 196),
        "bottom": (94, 168, 136),
        "accent": (30, 166, 111),
        "monitor": (37, 80, 63),
        "desk": (122, 194, 164),
    }


def _load_reference_avatar(reference_image: str, size: int = 92) -> Image.Image:
    try:
        if reference_image.startswith("http://") or reference_image.startswith("https://"):
            req = Request(reference_image, headers={"User-Agent": "clawpilot/scene-generator"})
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
            avatar = Image.open(io.BytesIO(raw)).convert("RGBA")
        else:
            avatar = Image.open(reference_image).convert("RGBA")
    except Exception:
        avatar = Image.new("RGBA", (size, size), (222, 222, 222, 255))
        draw = ImageDraw.Draw(avatar)
        draw.ellipse((0, 0, size - 1, size - 1), fill=(208, 208, 208, 255))
        return avatar

    fitted = ImageOps.fit(avatar, (size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    fitted.putalpha(mask)
    return fitted


def _generate_local_spritesheet(*, prompt: str, reference_image: str, output_path: Path) -> None:
    cols, rows = 4, 3
    width, height = 1536, 648
    cell_w, cell_h = width // cols, height // rows
    palette = _scene_palette_from_prompt(prompt)
    avatar = _load_reference_avatar(reference_image, size=92)

    canvas = Image.new("RGB", (width, height), palette["bottom"])
    for idx in range(cols * rows):
        frame = Image.new("RGB", (cell_w, cell_h), palette["bottom"])
        draw = ImageDraw.Draw(frame)

        for y in range(cell_h):
            t = y / max(1, cell_h - 1)
            draw.line((0, y, cell_w, y), fill=_lerp_color(palette["top"], palette["bottom"], t))

        draw.rounded_rectangle((12, 12, cell_w - 12, cell_h - 58), radius=16, fill=(245, 248, 252))
        draw.rounded_rectangle((cell_w - 168, 38, cell_w - 26, 115), radius=12, fill=palette["monitor"])
        draw.rounded_rectangle((26, cell_h - 56, cell_w - 26, cell_h - 20), radius=12, fill=palette["desk"])

        phase = idx / 12.0 * 2.0 * math.pi
        bob_x = int(4 * math.sin(phase))
        bob_y = int(6 * math.sin(phase * 1.2))
        frame.paste(avatar, (44 + bob_x, 70 + bob_y), avatar)

        blink = 0.55 + 0.45 * max(0.0, math.sin(phase * 1.7))
        bar = tuple(max(0, min(255, int(c * blink))) for c in palette["accent"])
        draw.rounded_rectangle((cell_w - 155, 52, cell_w - 40, 63), radius=5, fill=bar)
        draw.rounded_rectangle((cell_w - 155, 70, cell_w - 56, 80), radius=5, fill=bar)
        draw.rounded_rectangle((cell_w - 155, 87, cell_w - 66, 97), radius=5, fill=bar)

        ox = (idx % cols) * cell_w
        oy = (idx // cols) * cell_h
        canvas.paste(frame, (ox, oy))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")


def _generate_via_apimart(
    *,
    prompt: str,
    reference_image: str,
    output_path: Path,
    aspect_ratio: str,
    resolution: str,
    status_hook: StatusHook | None = None,
) -> None:
    api_url = os.getenv("AGENT_SCENE_APIMART_API_URL", "https://api.apimart.ai/v1/images/generations")
    task_url = os.getenv("AGENT_SCENE_APIMART_TASK_URL", "https://api.apimart.ai/v1/tasks")
    api_token = os.getenv("AGENT_SCENE_APIMART_API_TOKEN", "").strip()
    model = os.getenv("AGENT_SCENE_APIMART_MODEL", "gemini-2.5-flash-image-preview")
    poll_interval = int(os.getenv("AGENT_SCENE_APIMART_POLL_INTERVAL_SEC", "5"))
    max_retries = int(os.getenv("AGENT_SCENE_APIMART_POLL_MAX_RETRIES", "120"))
    if not api_token:
        raise RuntimeError("apimart_api_token_missing")

    headers = {"Authorization": f"Bearer {api_token}"}

    def poll_task(task_id: str) -> None:
        for _ in range(max_retries):
            time.sleep(poll_interval)
            status_data = _json_request(f"{task_url}/{task_id}", headers=headers, timeout=120)
            status = _extract_apimart_status(status_data)
            if status_hook:
                status_hook(
                    {
                        "provider": "apimart",
                        "phase": "poll",
                        "task_id": task_id,
                        "upstream_status": status or "unknown",
                    }
                )
            if status in {"completed", "succeeded", "success"}:
                image_url = _extract_apimart_image_url(status_data)
                if not image_url:
                    raise RuntimeError("apimart_completed_but_no_image")
                _download_to_file(image_url, output_path, timeout=180)
                return
            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"apimart_task_failed:{_extract_apimart_error(status_data)}")
        raise RuntimeError(f"apimart_task_timeout:{task_id}")

    cached_task_id = _get_cached_task_id(output_path)
    if cached_task_id:
        if status_hook:
            status_hook(
                {
                    "provider": "apimart",
                    "phase": "resume",
                    "task_id": cached_task_id,
                    "upstream_status": "resume",
                }
            )
        try:
            poll_task(cached_task_id)
            _clear_cached_task_id(output_path)
            return
        except RuntimeError as exc:
            # 超时保留 task_id，便于下次继续轮询；失败则清除。
            if not str(exc).startswith("apimart_task_timeout:"):
                _clear_cached_task_id(output_path)
            raise

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": aspect_ratio,
        "resolution": resolution,
        "image_urls": [_load_image_source(reference_image)],
    }

    try:
        submit = _json_request(api_url, method="POST", payload=payload, headers=headers, timeout=120)
    except Exception as exc:
        raise RuntimeError(f"apimart_submit_failed:{exc}") from exc

    task_id: str | None = None
    for candidate in (
        submit.get("id"),
        ((submit.get("data") or [{}])[0] if isinstance(submit.get("data"), list) else {}).get("task_id"),
        ((submit.get("data") or {}).get("task_id") if isinstance(submit.get("data"), dict) else None),
    ):
        if isinstance(candidate, str) and candidate.strip():
            task_id = candidate.strip()
            break
    if not task_id:
        raise RuntimeError(f"apimart_submit_failed:invalid_response:{submit}")

    _set_cached_task_id(output_path, task_id)
    if status_hook:
        status_hook(
            {
                "provider": "apimart",
                "phase": "submitted",
                "task_id": task_id,
                "upstream_status": "submitted",
            }
        )
    try:
        poll_task(task_id)
        _clear_cached_task_id(output_path)
        return
    except RuntimeError as exc:
        if not str(exc).startswith("apimart_task_timeout:"):
            _clear_cached_task_id(output_path)
        raise


def _generate_via_openrouter(
    *,
    prompt: str,
    reference_image: str,
    output_path: Path,
    aspect_ratio: str,
    resolution: str,
) -> None:
    api_url = os.getenv("AGENT_SCENE_OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
    api_key = os.getenv("AGENT_SCENE_OPENROUTER_API_KEY", "").strip()
    model = os.getenv("AGENT_SCENE_OPENROUTER_MODEL", "google/gemini-2.5-flash-image-preview")
    if not api_key:
        raise RuntimeError("openrouter_api_key_missing")

    source = _load_image_source(reference_image)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": source}},
                ],
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio, "image_size": resolution},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    data = _json_request(api_url, method="POST", payload=payload, headers=headers, timeout=180)
    image_url = _extract_openrouter_image(data)
    if not image_url:
        raise RuntimeError(f"openrouter_no_image:{data}")
    _download_to_file(image_url, output_path, timeout=180)


def generate_spritesheet(
    *,
    prompt: str,
    reference_image: str,
    output_path: Path,
    aspect_ratio: str,
    resolution: str,
    status_hook: StatusHook | None = None,
) -> dict[str, str]:
    provider = os.getenv("AGENT_SCENE_PROVIDER", "auto").strip().lower()
    enable_local_fallback = os.getenv("AGENT_SCENE_LOCAL_FALLBACK", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    if provider == "openrouter":
        try:
            _generate_via_openrouter(
                prompt=prompt,
                reference_image=reference_image,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
            )
            return {"engine": "openrouter"}
        except Exception as exc:
            errors.append(f"openrouter:{_compact_error_message(str(exc))}")
    elif provider == "apimart":
        try:
            _generate_via_apimart(
                prompt=prompt,
                reference_image=reference_image,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                status_hook=status_hook,
            )
            return {"engine": "apimart"}
        except Exception as exc:
            errors.append(f"apimart:{_compact_error_message(str(exc))}")
    else:
        try:
            _generate_via_apimart(
                prompt=prompt,
                reference_image=reference_image,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                status_hook=status_hook,
            )
            return {"engine": "apimart"}
        except Exception as exc:
            message = str(exc)
            errors.append(f"apimart:{_compact_error_message(message)}")
            # 仅 APIMart 提交前失败时才切到 OpenRouter，避免一个任务双通道重复扣费。
            if message.startswith("apimart_submit_failed:"):
                try:
                    _generate_via_openrouter(
                        prompt=prompt,
                        reference_image=reference_image,
                        output_path=output_path,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                    )
                    return {"engine": "openrouter"}
                except Exception as openrouter_exc:
                    errors.append(f"openrouter:{_compact_error_message(str(openrouter_exc))}")

    if errors and provider == "auto" and not enable_local_fallback:
        # 自动模式下仅在“提交前失败”时尝试过 OpenRouter，此处统一抛出汇总错误。
        raise RuntimeError(" | ".join(errors))

    if enable_local_fallback:
        if errors:
            print(f"[scene-generator] AI generation failed, fallback to local spritesheet: {' | '.join(errors)}")
        _generate_local_spritesheet(
            prompt=prompt,
            reference_image=reference_image,
            output_path=output_path,
        )
        return {"engine": "local_fallback", "detail": " | ".join(errors)}

    raise RuntimeError(" | ".join(errors) if errors else "image_generation_failed")


def crop_and_build_mp4(
    *,
    input_path: Path,
    output_mp4: Path,
    frames_dir: Path,
    metadata_path: Path,
    cols: int = 4,
    rows: int = 3,
    target_width: int = 1536,
    target_height: int = 648,
    fps: int = 4,
) -> None:
    if cols <= 0 or rows <= 0:
        raise RuntimeError("invalid_grid")
    if fps <= 0:
        raise RuntimeError("invalid_fps")

    im = Image.open(input_path).convert("RGB")
    if target_width > 0 and target_height > 0 and (im.width != target_width or im.height != target_height):
        im = im.resize((target_width, target_height), Image.Resampling.LANCZOS)

    cell_w = im.width // cols
    cell_h = im.height // rows
    if cell_w <= 0 or cell_h <= 0:
        raise RuntimeError("invalid_cell_size")

    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    frame_paths: list[str] = []

    index = 1
    for r in range(rows):
        for c in range(cols):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
            frame = im.crop(box)
            frame_path = frames_dir / f"frame-{index:02d}.png"
            frame.save(frame_path, format="PNG")
            frames.append(frame)
            frame_paths.append(str(frame_path))
            index += 1

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(
        str(output_mp4),
        fps=fps,
        codec="libx264",
        quality=8,
        pixelformat="yuv420p",
        macro_block_size=1,
    ) as writer:
        for frame in frames:
            writer.append_data(np.asarray(frame.convert("RGB")))

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source": str(input_path),
        "output_mp4": str(output_mp4),
        "frames_dir": str(frames_dir),
        "frame_count": len(frames),
        "frame_size": [cell_w, cell_h],
        "fps": fps,
        "target_width": target_width,
        "target_height": target_height,
        "frames": frame_paths,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
