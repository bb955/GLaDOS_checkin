"""Minimal, fail-closed GLaDOS check-in utility. No browser fingerprint evasion."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

import requests

ORIGIN = "https://glados.cloud"
STATUS_URL = f"{ORIGIN}/api/user/status"
CHECKIN_URL = f"{ORIGIN}/api/user/checkin"

# Server messages which have historically meant genuine success / already done.
SUCCESS_MARKERS = ("checkin!", "today's observation logged", "签到成功")
ALREADY_MARKERS = ("checkin repeats", "please try tomorrow", "今日已签到", "已经签到")
REJECTION_MARKERS = (
    "automated check-in detected", "please checkin via", "please sign in",
    "please login", "unauthorized", "没有权限", "请登录", "forbidden",
)


class CheckinError(Exception):
    """A controlled failure; never includes authentication material."""


@dataclass(frozen=True)
class Settings:
    cookie: str
    user_agent: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        cookie = os.getenv("GLADOS_COOKIE", "").strip()
        if not cookie:
            raise CheckinError("缺少 GLADOS_COOKIE（在仓库 Actions secrets 中配置）")
        if "\n" in cookie or "\r" in cookie:
            raise CheckinError("Cookie 包含非法换行")
        parts = {}
        for part in cookie.split(";"):
            name, separator, value = part.strip().partition("=")
            if separator:
                parts[name] = value
        if not parts.get("gld:sess") or not parts.get("gld:sess.sig"):
            raise CheckinError("Cookie 不包含完整的 gld:sess 和 gld:sess.sig")

        agent = (os.getenv("GLADOS_USER_AGENT") or os.getenv("GLADOS_UA") or "").strip() or None
        if agent and ("\r" in agent or "\n" in agent):
            raise CheckinError("GLADOS_USER_AGENT 包含非法换行")
        return cls(cookie=cookie, user_agent=agent)


def api_json(session: requests.Session, method: str, endpoint: str,
             headers: dict[str, str], **kwargs: Any) -> dict[str, Any]:
    try:
        response = session.request(
            method, endpoint, headers=headers, timeout=(5, 20),
            allow_redirects=False, **kwargs,
        )
        # Do not follow redirects with authentication cookies.
        if 300 <= response.status_code < 400:
            raise CheckinError(f"GLaDOS 返回 HTTP {response.status_code} 重定向，已停止")
        response.raise_for_status()
        obj = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CheckinError(f"GLaDOS 请求失败（{type(exc).__name__}），请检查网络或会话") from None
    if not isinstance(obj, dict):
        raise CheckinError("GLaDOS 未返回 JSON 对象")
    return obj


def classify_checkin(payload: dict[str, Any]) -> str:
    code = str(payload.get("code", "missing"))
    message = str(payload.get("message") or "").strip().lower()
    if code == "4":
        # Only report a known, non-sensitive reason. Never log the response body,
        # account identifiers, cookies or the complete device fingerprint.
        reason = payload.get("reason")
        reason_hint = (
            "服务端报告登录设备平台不一致（reason=device-mismatch）。"
            if reason == "device-mismatch" else
            "服务端未提供可确定的设备不匹配原因。"
        )
        raise CheckinError(
            f"GLaDOS 拒绝自动签到（code=4）。{reason_hint}"
            "当前 Cookie 虽可能有效，但应核对与登录会话一致的 GLADOS_USER_AGENT。"
            "若仍被拒绝，应通过官方网页签到；不会自动重试或误报成功"
        )
    if any(mark in message for mark in REJECTION_MARKERS):
        raise CheckinError(
            f"GLaDOS 服务端拒绝签到请求（code={code}）。"
            "Cookie 即使能查询账号，也不代表服务端允许自动签到。"
            "若仍被拒绝，应通过官方网页手动签到，不会自动重试"
        )
    if code in {"0", "1"} and any(mark in message for mark in ALREADY_MARKERS):
        return "今日已签到"
    if code == "0" and any(mark in message for mark in SUCCESS_MARKERS):
        return "签到成功"
    raise CheckinError(f"服务端没有确认签到成功（code={code}），不将任务标记为成功")


def run(mode: str, settings: Settings, session: requests.Session | None = None) -> str:
    if mode not in {"status", "checkin"}:
        raise CheckinError("只允许 status 和 checkin 模式")
    # Deliberately use the *actual* browser UA, not a guessed browser fingerprint.
    # A basic UA is sufficient for an account-status-only diagnostic.
    if mode == "checkin" and not settings.user_agent:
        raise CheckinError(
            "缺少 GLADOS_USER_AGENT。请在取得 Cookie 的同一浏览器中运行 navigator.userAgent，"
            "把结果保存到本仓库 Settings → Secrets and variables → Actions → Variables，"
            "变量名 GLADOS_USER_AGENT；未配置前不会发送签到请求"
        )

    headers = {
        "Cookie": settings.cookie,
        "User-Agent": settings.user_agent or "Mozilla/5.0",
        "Origin": ORIGIN,
        "Referer": f"{ORIGIN}/console/checkin",
        "Content-Type": "application/json;charset=UTF-8",
    }
    created = session is None
    session = session or requests.Session()
    try:
        status = api_json(session, "GET", STATUS_URL, headers)
        if str(status.get("code")) != "0" or not isinstance(status.get("data"), dict):
            raise CheckinError("登录状态校验失败：当前 Cookie 未获账号状态接口认可")
        if mode == "status":
            return "Cookie 有效：账号状态查询通过（未发送签到请求）"
        result = api_json(session, "POST", CHECKIN_URL, headers, json={"token": "glados.cloud"})
        return classify_checkin(result)
    finally:
        if created:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="GLaDOS account check-in")
    parser.add_argument("--mode", choices=["checkin", "status"], default="checkin")
    args = parser.parse_args()
    try:
        result = run(args.mode, Settings.from_env())
        print(result)
        return 0
    except CheckinError as exc:
        print(f"::error::GLaDOS 签到未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
