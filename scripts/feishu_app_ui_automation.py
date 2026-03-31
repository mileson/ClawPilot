#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

OPEN_FEISHU_ORIGIN = "https://open.feishu.cn"
DEFAULT_URL = f"{OPEN_FEISHU_ORIGIN}/page/openclaw?form=multiAgent"
DEFAULT_APP_NAME = "Clawpilot"
DEFAULT_APP_DESCRIPTION = "第一只小龙虾，负责统管所有业务"
DEFAULT_MENU_NAME = "/status 状态"
DEFAULT_PROFILE_DIR = str(Path.home() / ".clawpilot" / "feishu-ui-profile")
DEFAULT_CDP_HTTP_ENDPOINTS = (
    "http://127.0.0.1:9222",
    "http://127.0.0.1:9223",
    "http://127.0.0.1:9333",
    "http://127.0.0.1:9334",
)
OPENCLAW_TEMPLATE_PATH = "/developers/v1/app_registration/openclaw_app_config_template"
LOGIN_CHECK_PATH = "/napi/check/login"
MANIFEST_UPSERT_TEMPLATE_PATH = "/developers/v1/manifest/upsert_by_template"
APP_SECRET_PATH_TEMPLATE = "/developers/v1/secret/{app_id}"
APP_VERSION_CREATE_PATH_TEMPLATE = "/developers/v1/app_version/create/{app_id}"
PUBLISH_COMMIT_PATH_TEMPLATE = "/developers/v1/publish/commit/{app_id}/{version_id}"
APP_DETAIL_PATH_TEMPLATE = "/developers/v1/app/{app_id}"
CHAT_URL_TEMPLATE = "https://applink.feishu.cn/client/bot/open?appId={app_id}"


def _build_chat_url(app_id: str | None) -> str | None:
    if not app_id:
        return None
    return CHAT_URL_TEMPLATE.format(app_id=app_id)


def _emit(payload: dict) -> None:
    normalized = {
        "status": "failed",
        "step": None,
        "message": None,
        "app_id": None,
        "app_secret": None,
        "chat_url": None,
        "execution_mode": None,
        "debugger_url": None,
    }
    normalized.update(payload)
    if not normalized.get("chat_url"):
        normalized["chat_url"] = _build_chat_url(normalized.get("app_id"))
    print(json.dumps(normalized, ensure_ascii=False))
    sys.exit(0)


def _fail(step: str, message: str, *, execution_mode: str | None = None, debugger_url: str | None = None) -> None:
    _emit(
        {
            "status": "failed",
            "step": step,
            "message": message,
            "execution_mode": execution_mode,
            "debugger_url": debugger_url,
        }
    )


def _safe_click(locator, timeout: int = 10000) -> None:
    locator.first.wait_for(state="visible", timeout=timeout)
    locator.first.click()


def _safe_fill(locator, value: str, timeout: int = 10000) -> None:
    locator.first.wait_for(state="visible", timeout=timeout)
    locator.first.fill(value)


def _locator_text_or_none(locator) -> str | None:
    try:
        text = locator.first.inner_text().strip()
        return text or None
    except Exception:
        return None


def _read_clipboard(page) -> str | None:
    try:
        value = page.evaluate("() => navigator.clipboard.readText()")
    except Exception:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _read_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _extract_named_string(payload, keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and isinstance(value, str) and value.strip():
                return value.strip()
            found = _extract_named_string(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_named_string(item, keys)
            if found:
                return found
    elif isinstance(payload, str):
        stripped = payload.strip()
        if stripped and len(stripped) >= 16:
            return stripped
    return None


def _extract_app_id(payload) -> str | None:
    if isinstance(payload, str):
        match = re.search(r"\bcli_[A-Za-z0-9]+\b", payload)
        return match.group(0) if match else None
    if isinstance(payload, dict):
        for value in payload.values():
            found = _extract_app_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_app_id(item)
            if found:
                return found
    return None


def _extract_app_secret(payload) -> str | None:
    value = _extract_named_string(payload, {"appSecret", "app_secret", "secret", "clientSecret"})
    if value and "*" not in value:
        return value
    return None


def _extract_client_id(payload) -> str | None:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("clientID", "clientId", "appID", "appId"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return _extract_app_id(payload)


def _extract_version_id(payload) -> str | None:
    if isinstance(payload, str):
        match = re.search(r'"versionId"\s*:\s*"(\d+)"', payload)
        return match.group(1) if match else None
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("versionId", "versionID"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for value in payload.values():
            found = _extract_version_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_version_id(item)
            if found:
                return found
    return None


def _normalize_cdp_candidate(candidate: str) -> str | None:
    value = (candidate or "").strip()
    if not value:
        return None
    if value.startswith(("ws://", "wss://", "http://", "https://")):
        return value.rstrip("/")
    if value.isdigit():
        return f"http://127.0.0.1:{value}"
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return value.rstrip("/")
    return f"http://{value}".rstrip("/")


def _list_remote_debugging_candidates_from_processes() -> list[str]:
    try:
        output = subprocess.check_output(["ps", "aux"], text=True)
    except Exception:
        return []

    preferred: list[str] = []
    regular: list[str] = []
    seen: set[str] = set()

    for line in output.splitlines():
        if "--remote-debugging-port=" not in line:
            continue
        match = re.search(r"--remote-debugging-port=(\d+)", line)
        if not match:
            continue
        endpoint = f"http://127.0.0.1:{match.group(1)}"
        if endpoint in seen:
            continue
        seen.add(endpoint)
        lowered = line.lower()
        if "mcp-chrome" in lowered or "playwright" in lowered:
            preferred.append(endpoint)
        else:
            regular.append(endpoint)
    return preferred + regular


def _probe_cdp_candidate(candidate: str, *, timeout_sec: float = 1.5) -> dict | None:
    normalized = _normalize_cdp_candidate(candidate)
    if not normalized:
        return None
    if normalized.startswith(("ws://", "wss://")):
        return {"endpoint": normalized, "debugger_url": normalized}

    version_url = f"{normalized}/json/version"
    request = Request(version_url, headers={"User-Agent": "ClawPilot/feishu-ui-automation"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None

    debugger_url = payload.get("webSocketDebuggerUrl") or normalized
    return {
        "endpoint": debugger_url,
        "debugger_url": debugger_url,
    }


def _discover_cdp_target(explicit_candidate: str | None) -> dict | None:
    candidates: list[str] = []
    if explicit_candidate:
        candidates.append(explicit_candidate)
    candidates.extend(DEFAULT_CDP_HTTP_ENDPOINTS)
    candidates.extend(_list_remote_debugging_candidates_from_processes())

    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_cdp_candidate(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved = _probe_cdp_candidate(normalized)
        if resolved:
            return resolved
    return None


def _open_target_page(context, url: str):
    for page in context.pages:
        if "open.feishu.cn" in page.url or "accounts.feishu.cn" in page.url:
            try:
                page.bring_to_front()
            except Exception:
                pass
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return page, False
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    return page, True


def _resolve_runtime(playwright, args):
    if args.automation_mode in {"auto", "cdp"}:
        cdp_target = _discover_cdp_target(args.cdp_url)
        if cdp_target:
            browser = playwright.chromium.connect_over_cdp(cdp_target["endpoint"], timeout=15000)
            if not browser.contexts:
                _fail(
                    "cdp_attach",
                    "已连接 Chrome 调试端口，但未发现可复用的浏览器上下文",
                    execution_mode="cdp",
                    debugger_url=cdp_target["debugger_url"],
                )
            context = browser.contexts[0]
            try:
                context.grant_permissions(["clipboard-read", "clipboard-write"], origin=OPEN_FEISHU_ORIGIN)
            except Exception:
                pass
            return {
                "execution_mode": "cdp",
                "debugger_url": cdp_target["debugger_url"],
                "browser": browser,
                "context": context,
            }
        if args.automation_mode == "cdp":
            _fail(
                "cdp_attach",
                "未发现可附着的 Chrome 调试端口。请使用带 --remote-debugging-port 的 Chrome，或改用独立 profile 模式。",
                execution_mode=None,
                debugger_url=None,
            )

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=args.profile_dir,
        headless=args.headless,
        args=["--lang=zh-CN"],
    )
    try:
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=OPEN_FEISHU_ORIGIN)
    except Exception:
        pass
    return {
        "execution_mode": "profile",
        "debugger_url": None,
        "browser": None,
        "context": context,
    }


def _browser_fetch(page, path: str, *, method: str = "GET", body=None):
    url = path if path.startswith("http://") or path.startswith("https://") else f"{OPEN_FEISHU_ORIGIN}{path}"
    return page.evaluate(
        """
        async ({ url, method, body }) => {
          try {
            const csrfToken =
              globalThis.csrfToken ||
              globalThis.__INITIAL_STATE__?.csrfToken ||
              globalThis.__APP_DATA__?.csrfToken ||
              "";
            const headers = {
              "accept": "application/json, text/plain, */*",
              "X-Timezone-Offset": String(new Date().getTimezoneOffset()),
            };
            if (csrfToken) {
              headers["x-csrf-token"] = csrfToken;
            }
            let requestBody = undefined;
            if (body !== null) {
              headers["content-type"] = "application/json";
              requestBody = JSON.stringify(body);
            }
            const response = await fetch(url, {
              method,
              headers,
              body: requestBody,
              credentials: "include",
            });
            const text = await response.text();
            let data = null;
            try {
              data = text ? JSON.parse(text) : null;
            } catch (error) {
              data = null;
            }
            return {
              ok: response.ok,
              status: response.status,
              text,
              data,
              url: response.url,
            };
          } catch (error) {
            return {
              ok: false,
              status: 0,
              text: "",
              data: null,
              url,
              error: String(error),
            };
          }
        }
        """,
        {"url": url, "method": method, "body": body},
    )


def _is_login_response_ok(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("code") not in (0, "0", None):
        return False
    data = payload.get("data")
    return isinstance(data, dict) and bool(data.get("id"))


def _is_logged_in(page) -> bool:
    if "accounts.feishu.cn" in page.url:
        return False
    try:
        login_payload = _browser_fetch(page, LOGIN_CHECK_PATH, method="POST", body={})
        if isinstance(login_payload, dict) and login_payload.get("ok") and _is_login_response_ok(login_payload.get("data")):
            return True
    except Exception:
        pass
    text = _read_body_text(page)
    if "扫码登录" in text or "手机号登录" in text:
        return False
    return "创建 OpenClaw 飞书机器人" in text or bool(re.search(r"复制\s*App ID", text))


def _has_openclaw_access(page) -> bool:
    if _is_logged_in(page):
        return True
    try:
        return _probe_openclaw_template(page)
    except Exception:
        return False


def _probe_openclaw_template(page) -> bool:
    try:
        payload = _browser_fetch(page, OPENCLAW_TEMPLATE_PATH)
    except Exception:
        return False
    if not isinstance(payload, dict) or not payload.get("ok"):
        return False
    data = payload.get("data")
    return isinstance(data, dict)


def _wait_for_openclaw_page_ready(page, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        () => {
          const text = document.body?.innerText || "";
          const hasTitle = text.includes("创建 OpenClaw 飞书机器人");
          const hasSuccess = text.includes("创建成功") || /复制\\s*App ID/.test(text);
          const hasInput = !!document.querySelector("input");
          return hasSuccess || (hasTitle && hasInput);
        }
        """,
        timeout=timeout_ms,
    )
    time.sleep(0.6)


def _wait_for_login(page, target_url: str, timeout_ms: int) -> bool:
    deadline = time.time() + max(timeout_ms, 1000) / 1000
    next_probe_at = 0.0
    while time.time() < deadline:
        if _has_openclaw_access(page):
            try:
                if not page.url.startswith(target_url):
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(1.0)
            except Exception:
                pass
            return _has_openclaw_access(page)
        current_url = (getattr(page, "url", "") or "").strip()
        should_probe_target = (
            not current_url
            or "accounts.feishu.cn" in current_url
            or "open.feishu.cn" not in current_url
        )
        now = time.time()
        if should_probe_target and now >= next_probe_at:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(0.6)
                if _has_openclaw_access(page):
                    return True
            except Exception:
                pass
            next_probe_at = now + 4.0
        time.sleep(0.8)
    return False


def _normalize_asset_url(value: str | None) -> str | None:
    url = (value or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{OPEN_FEISHU_ORIGIN}{url}"
    return url


def _selected_openclaw_avatar_url(page) -> str | None:
    try:
        locator = page.locator("img[alt='avatar']")
        if locator.count() > 0:
            src = locator.first.get_attribute("src")
            normalized = _normalize_asset_url(src)
            if normalized:
                return normalized
    except Exception:
        pass

    try:
        src = page.evaluate(
            """
            () => {
              const candidates = Array.from(document.querySelectorAll("img"))
                .map((img) => {
                  const rect = img.getBoundingClientRect();
                  return {
                    src: img.getAttribute("src") || "",
                    width: rect.width,
                    height: rect.height,
                    y: rect.y,
                  };
                })
                .filter((item) => item.src && item.width >= 60 && item.height >= 60 && item.y > 200);
              return candidates[0]?.src || "";
            }
            """
        )
        normalized = _normalize_asset_url(src)
        if normalized:
            return normalized
    except Exception:
        pass
    return None


def _build_openclaw_manifest_payload(app_name: str, app_description: str, avatar_url: str | None) -> dict:
    return {
        "appManifestTemplateID": "openclaw_plugin_template",
        "createAppUserCustomField": {
            "i18n": {
                "zh_cn": {
                    "name": app_name,
                    "description": app_description,
                }
            },
            "avatar": avatar_url or "",
            "primaryLang": "zh_cn",
        },
        "cid": f"c{secrets.token_hex(12)}",
        "HTTPHead": {},
    }


def _fill_openclaw_name(page, app_name: str) -> None:
    candidates = [
        page.get_by_label("名称"),
        page.locator("input").first,
    ]
    for locator in candidates:
        try:
            if locator.count() == 0:
                continue
            _safe_fill(locator, app_name)
            return
        except Exception:
            continue
    raise RuntimeError("未找到 OpenClaw 创建页的名称输入框")


def _wait_for_openclaw_success(page, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        () => {
          const text = document.body?.innerText || "";
          return text.includes("创建成功") || /复制\\s*App ID/.test(text);
        }
        """,
        timeout=timeout_ms,
    )
    time.sleep(0.8)


def _copy_value_from_button(page, pattern: str) -> str | None:
    locator = page.get_by_role("button", name=re.compile(pattern))
    if locator.count() == 0:
        return None
    try:
        locator.first.click()
        time.sleep(0.5)
    except Exception:
        return None
    return _read_clipboard(page)


def _read_created_app_id(page) -> str | None:
    body_text = _read_body_text(page)
    match = re.search(r"\bcli_[A-Za-z0-9]+\b", body_text)
    if match:
        return match.group(0)
    copied = _copy_value_from_button(page, r"复制\s*App ID")
    return _extract_app_id(copied)


def _fetch_app_secret_via_browser_api(page, app_id: str, *, timeout_sec: int = 15) -> str | None:
    deadline = time.time() + max(timeout_sec, 1)
    while time.time() < deadline:
        payload = _browser_fetch(page, APP_SECRET_PATH_TEMPLATE.format(app_id=app_id))
        if isinstance(payload, dict) and payload.get("ok"):
            secret = _extract_app_secret(payload.get("data"))
            if secret:
                return secret
            secret = _extract_app_secret(payload.get("text"))
            if secret:
                return secret
        time.sleep(1.0)
    return None


def _fetch_app_detail_via_browser_api(page, app_id: str) -> dict | None:
    payload = _browser_fetch(page, APP_DETAIL_PATH_TEMPLATE.format(app_id=app_id), method="POST", body={})
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _is_app_online(detail: dict | None) -> bool:
    if not isinstance(detail, dict):
        return False
    return detail.get("appListStatus") == 2 and detail.get("tenantAppStatus") == 2


def _create_app_version_via_browser_api(page, app_id: str) -> str:
    payload = _browser_fetch(page, APP_VERSION_CREATE_PATH_TEMPLATE.format(app_id=app_id), method="POST", body={})
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"app_version_create_failed:{json.dumps(payload, ensure_ascii=False)}")
    response_data = payload.get("data")
    if not isinstance(response_data, dict) or response_data.get("code") not in (0, "0", None):
        raise RuntimeError(f"app_version_create_rejected:{payload.get('text') or response_data}")
    version_id = _extract_version_id(response_data) or _extract_version_id(payload.get("text"))
    if not version_id:
        raise RuntimeError("app_version_create_missing_version_id")
    return version_id


def _publish_app_version_via_browser_api(page, app_id: str, version_id: str) -> None:
    payload = _browser_fetch(
        page,
        PUBLISH_COMMIT_PATH_TEMPLATE.format(app_id=app_id, version_id=version_id),
        method="POST",
        body={},
    )
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"publish_commit_failed:{json.dumps(payload, ensure_ascii=False)}")
    response_data = payload.get("data")
    if not isinstance(response_data, dict) or response_data.get("code") not in (0, "0", None):
        raise RuntimeError(f"publish_commit_rejected:{payload.get('text') or response_data}")
    payload_data = response_data.get("data")
    if isinstance(payload_data, dict) and payload_data.get("isOk") is False:
        raise RuntimeError(f"publish_commit_not_ready:{json.dumps(payload_data, ensure_ascii=False)}")


def _wait_for_app_online(page, app_id: str, *, timeout_sec: int) -> bool:
    deadline = time.time() + max(timeout_sec, 1)
    while time.time() < deadline:
        if _is_app_online(_fetch_app_detail_via_browser_api(page, app_id)):
            return True
        time.sleep(1.0)
    return False


def _post_create_online_grace_timeout(total_timeout_sec: int) -> int:
    return min(max(total_timeout_sec // 120, 2), 3)


def _ensure_app_online(page, app_id: str, *, timeout_sec: int) -> None:
    if _is_app_online(_fetch_app_detail_via_browser_api(page, app_id)):
        return
    version_id = _create_app_version_via_browser_api(page, app_id)
    _publish_app_version_via_browser_api(page, app_id, version_id)
    if not _wait_for_app_online(page, app_id, timeout_sec=timeout_sec):
        raise RuntimeError("publish_commit_timeout")


def _read_created_app_secret(page) -> str | None:
    copied = _copy_value_from_button(page, r"复制\s*App Secret")
    if copied and "*" not in copied:
        return copied
    return None


def _create_openclaw_via_browser_api(page, args, runtime: dict) -> dict[str, str | None]:
    if not _probe_openclaw_template(page):
        raise RuntimeError("openclaw_template_unavailable")

    payload = _build_openclaw_manifest_payload(
        app_name=args.app_name,
        app_description=args.app_description,
        avatar_url=_selected_openclaw_avatar_url(page),
    )
    create_payload = _browser_fetch(page, MANIFEST_UPSERT_TEMPLATE_PATH, method="POST", body=payload)
    if not isinstance(create_payload, dict) or not create_payload.get("ok"):
        raise RuntimeError(f"manifest_upsert_failed:{json.dumps(create_payload, ensure_ascii=False)}")

    response_data = create_payload.get("data")
    if not isinstance(response_data, dict) or response_data.get("code") not in (0, "0", None):
        raise RuntimeError(f"manifest_upsert_rejected:{create_payload.get('text') or response_data}")

    app_id = _extract_client_id(response_data) or _extract_app_id(create_payload.get("text"))
    if not app_id:
        raise RuntimeError("manifest_upsert_missing_client_id")

    app_secret = _fetch_app_secret_via_browser_api(page, app_id, timeout_sec=min(max(args.timeout_sec // 4, 10), 30))
    if not app_secret:
        raise RuntimeError("manifest_upsert_missing_app_secret")

    # Keep the success page open briefly so Feishu can finish its own
    # asynchronous auto-publish flow. This avoids returning too early while
    # also avoiding false-negative failures when the detail endpoint lags.
    _wait_for_app_online(page, app_id, timeout_sec=_post_create_online_grace_timeout(args.timeout_sec))

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "chat_url": _build_chat_url(app_id),
    }


def _should_fallback_to_ui(create_error: str | None) -> bool:
    reason = (create_error or "").strip()
    if not reason:
        return False
    non_fallback_errors = (
        "manifest_upsert_missing_client_id",
        "manifest_upsert_missing_app_secret",
        "capture_credentials",
    )
    return not any(item in reason for item in non_fallback_errors)


def _create_openclaw_via_new_page(page, args, runtime: dict) -> dict[str, str | None]:
    _fill_openclaw_name(page, args.app_name)
    _safe_click(page.get_by_role("button", name="创建", exact=True))
    _wait_for_openclaw_success(page, timeout_ms=args.timeout_sec * 1000)

    app_id = _read_created_app_id(page)
    if not app_id:
        _fail(
            "capture_credentials",
            "新创建页已完成，但未能读取 App ID",
            execution_mode=runtime["execution_mode"],
            debugger_url=runtime["debugger_url"],
        )

    app_secret = _first_non_empty(
        _fetch_app_secret_via_browser_api(page, app_id, timeout_sec=min(max(args.timeout_sec // 4, 10), 30)),
        _read_created_app_secret(page),
    )
    if not app_secret:
        _fail(
            "capture_credentials",
            "新创建页已完成，但未能读取 App Secret",
            execution_mode=runtime["execution_mode"],
            debugger_url=runtime["debugger_url"],
        )

    # The success page itself will continue Feishu's auto-publish flow in the
    # background. Keep the page alive briefly, but don't fail the run if the
    # status endpoint lags behind the UI's eventual "已启用" result.
    _wait_for_app_online(page, app_id, timeout_sec=_post_create_online_grace_timeout(args.timeout_sec))

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "chat_url": _build_chat_url(app_id),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--app-description", default=DEFAULT_APP_DESCRIPTION)
    parser.add_argument("--menu-name", default=DEFAULT_MENU_NAME)
    parser.add_argument("--automation-mode", default="auto", choices=("auto", "cdp", "profile"))
    parser.add_argument("--cdp-url", default=None)
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-for-login", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=180)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "playwright"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
            )
            from playwright.sync_api import sync_playwright
        except Exception:
            _emit(
                {
                    "status": "dependency_missing",
                    "step": "init",
                    "message": "自动安装 playwright 失败，请手动执行 `pip install playwright` 并执行 `playwright install chromium`",
                }
            )

    created_page = False
    page = None
    runtime = None

    try:
        with sync_playwright() as playwright:
            runtime = _resolve_runtime(playwright, args)
            context = runtime["context"]
            page, created_page = _open_target_page(context, args.url)
            time.sleep(1.5)

            if not _has_openclaw_access(page):
                if args.wait_for_login:
                    login_detected = _wait_for_login(page, args.url, timeout_ms=args.timeout_sec * 1000)
                    if not login_detected:
                        _emit(
                            {
                                "status": "login_required",
                                "step": "login_wait_timeout",
                                "message": "在等待时间内未检测到飞书开放平台登录完成，请重试",
                                "execution_mode": runtime["execution_mode"],
                                "debugger_url": runtime["debugger_url"],
                            }
                        )
                else:
                    _emit(
                        {
                            "status": "login_required",
                            "step": "login_check",
                            "message": "未检测到飞书开放平台登录态，请先登录后重试",
                            "execution_mode": runtime["execution_mode"],
                            "debugger_url": runtime["debugger_url"],
                        }
                    )

            _wait_for_openclaw_page_ready(page, timeout_ms=min(args.timeout_sec * 1000, 20000))

            create_error: str | None = None
            try:
                # Match the real UI flow so the created app reaches "已启用/已发布"
                # instead of stopping at a draft-like "待上线" state.
                result = _create_openclaw_via_new_page(page, args, runtime)
            except Exception as exc:
                create_error = str(exc)
                _fail(
                    "create_openclaw",
                    create_error,
                    execution_mode=runtime["execution_mode"],
                    debugger_url=runtime["debugger_url"],
                )
            _emit(
                {
                    "status": "success",
                    "step": "done",
                    "message": "ok" if not create_error else f"ok:fallback_from_api:{create_error}",
                    "app_id": result["app_id"],
                    "app_secret": result["app_secret"],
                    "chat_url": result["chat_url"],
                    "execution_mode": runtime["execution_mode"],
                    "debugger_url": runtime["debugger_url"],
                }
            )
    except Exception as exc:
        _fail(
            "automation",
            str(exc),
            execution_mode=(runtime or {}).get("execution_mode"),
            debugger_url=(runtime or {}).get("debugger_url"),
        )
    finally:
        try:
            if runtime and runtime["execution_mode"] == "profile":
                runtime["context"].close()
        except Exception:
            pass
        try:
            if runtime and runtime["execution_mode"] == "cdp" and created_page and page is not None:
                page.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
