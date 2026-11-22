"""Run GLaDOS check-in through its official page in a real, visible browser.

This script is intended for a self-hosted macOS GitHub Actions runner running
inside an interactive logged-in desktop session. It does not forge browser
fingerprints, extract or replay Turnstile tokens, or call the check-in API
itself. The official page performs its normal verification and submission.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from checkin import CheckinError, classify_checkin

ORIGIN = "https://glados.cloud"
CHECKIN_PAGE = f"{ORIGIN}/console/checkin"
CHECKIN_API = f"{ORIGIN}/api/user/checkin"
BUTTON_NAME = re.compile(r"check[\s-]*in|签到", re.IGNORECASE)
LOGIN_AND_CHALLENGE_WAIT_SECONDS = 300
RESULT_WAIT_SECONDS = 180


def classify_browser_response(payload: dict[str, Any]) -> str:
    """Use the same strict, fail-closed success rules as the API client."""
    return classify_checkin(payload)


def browser_profile_dir() -> Path:
    configured = os.environ.get("GLADOS_BROWSER_PROFILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "GLaDOSCheckin"
        / "ChromiumProfile"
    )


def run_browser_checkin() -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise CheckinError(
            "缺少 Playwright。请在 Mac runner 上安装 requirements-browser.txt"
        ) from exc

    profile = browser_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    captured: dict[str, Any] = {}

    with sync_playwright() as playwright:
        context = None
        try:
            # Keep the browser visible and use its normal browser identity.
            # If Turnstile asks for interaction, the user can complete it here.
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
            )
            page = context.new_page()

            def capture_checkin_response(response: Any) -> None:
                try:
                    if (
                        response.url.split("?", 1)[0] == CHECKIN_API
                        and response.request.method == "POST"
                    ):
                        try:
                            body = response.json()
                            captured["payload"] = (
                                body if isinstance(body, dict)
                                else {"code": "invalid", "message": "invalid response"}
                            )
                        except Exception:  # noqa: BLE001 - never print raw response
                            captured["payload"] = {
                                "code": "invalid",
                                "message": "non-json response",
                            }
                except Exception:  # noqa: BLE001 - response observer must not crash page
                    pass

            page.on("response", capture_checkin_response)
            page.goto(
                CHECKIN_PAGE,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            print(
                "已打开 GLaDOS 官方签到页。首次运行请在浏览器窗口中登录；"
                "若出现 Turnstile，请本人完成页面要求的验证。",
                flush=True,
            )

            button = page.get_by_role("button", name=BUTTON_NAME).first
            deadline = time.monotonic() + LOGIN_AND_CHALLENGE_WAIT_SECONDS
            while time.monotonic() < deadline:
                if "payload" in captured:
                    return classify_browser_response(captured["payload"])
                try:
                    if button.count() > 0 and button.is_visible() and not button.is_disabled():
                        break
                except Exception:  # noqa: BLE001 - SPA may still be rendering
                    pass
                page.wait_for_timeout(1_000)
            else:
                raise CheckinError(
                    "5 分钟内没有出现可用的官方签到按钮。请检查浏览器是否仍停留在登录页，"
                    "并确认已完成页面要求的验证；本次没有确认签到成功"
                )

            # Click once only. Any Turnstile interaction is left to the official
            # widget and, if required, the person at the Mac.
            print("官方签到按钮已就绪，点击一次并等待官网返回结果。", flush=True)
            try:
                button.click(timeout=15_000)
            except PlaywrightTimeoutError as exc:
                raise CheckinError(
                    "点击官方签到按钮超时；请查看 Mac 上的浏览器窗口"
                ) from exc

            deadline = time.monotonic() + RESULT_WAIT_SECONDS
            while time.monotonic() < deadline:
                if "payload" in captured:
                    return classify_browser_response(captured["payload"])
                page.wait_for_timeout(500)

            raise CheckinError(
                "点击后 180 秒内没有收到官网签到结果。若页面出现 Turnstile，"
                "请在浏览器窗口中完成验证后重新运行；本次不报成功"
            )
        except CheckinError:
            raise
        except Exception as exc:  # noqa: BLE001 - avoid leaking page/session details
            raise CheckinError(
                f"真实浏览器运行失败（{type(exc).__name__}）。"
                "请确认 Mac runner 正在已登录的图形桌面会话中运行"
            ) from None
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:  # noqa: BLE001
                    pass


def main() -> int:
    try:
        print(run_browser_checkin(), flush=True)
        return 0
    except CheckinError as exc:
        print(f"::error::GLaDOS 浏览器签到未完成：{exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
