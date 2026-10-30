"""GLaDOS daily check-in with an explicit success/failure exit status."""

import os
import sys
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests


DEFAULT_ORIGIN = "https://glados.cloud"
ALLOWED_HOSTS = {
    "glados.cloud",
    "glados.rocks",
    "glados.network",
    "glados.one",
    "glados.space",
    "glados.vip",
    "glados-facility.com",
}
ALREADY_MESSAGES = ("checkin repeats", "please try tomorrow", "今日已签到", "已经签到")
SUCCESS_MESSAGES = ("checkin!", "today's observation logged", "签到成功")
ERROR_MESSAGES = (
    "automated check-in detected",
    "please checkin via",
    "没有权限",
    "unauthorized",
    "please login",
    "please sign in",
    "请登录",
    "forbidden",
)


def get_origin():
    origin = (os.environ.get("GLADOS_ORIGIN") or DEFAULT_ORIGIN).strip().rstrip("/")
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.path
        or parsed.port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("GLADOS_ORIGIN 必须是支持的 GLaDOS HTTPS 主站域名")
    return origin


def get_user_agent():
    # Newer GLaDOS sessions may be tied to the login browser platform.
    # Never invent a browser identity: use the one configured by the account owner.
    ua = (os.environ.get("GLADOS_USER_AGENT") or os.environ.get("GLADOS_UA") or "").strip()
    if not ua or ua == "Mozilla/5.0":
        raise ValueError(
            "缺少有效的 GLADOS_USER_AGENT。请填写取得 Cookie 时同一浏览器的完整 User-Agent；"
            "未配置前不请求 GLaDOS 签到接口"
        )
    if "\\r" in ua or "\\n" in ua:
        raise ValueError("GLADOS_USER_AGENT 包含非法换行")
    return ua


def validate_cookie(cookie):
    fields = {}
    for part in cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator:
            fields[name] = value
    if not (fields.get("gld:sess") and fields.get("gld:sess.sig")):
        raise ValueError("GLADOS_COOKIE 缺少 gld:sess 或 gld:sess.sig，请刷新完整登录 Cookie")


def request_json(session, method, url, **kwargs):
    response = session.request(method, url, timeout=20, **kwargs)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("GLaDOS 接口未返回预期的 JSON 对象")
    return result


def short_message(result):
    # Never log complete responses: they may contain private account data.
    return str(result.get("message") or "无具体说明").replace("\n", " ").replace("\r", " ")[:160]


def masked_email(address):
    if not isinstance(address, str) or "@" not in address:
        return "未知"
    local, domain = address.rsplit("@", 1)
    return f"{local[:2]}***@{domain}"


def check_in():
    cookie = os.environ.get("GLADOS_COOKIE", "").strip()
    if not cookie:
        raise ValueError("未配置 GLADOS_COOKIE：请在仓库 Actions Secrets 中添加或更新")

    validate_cookie(cookie)
    user_agent = get_user_agent()
    origin = get_origin()
    host = urlparse(origin).hostname
    headers = {
        "cookie": cookie,
        "user-agent": user_agent,
        "referer": f"{origin}/console/checkin",
        "origin": origin,
        "content-type": "application/json;charset=UTF-8",
    }

    with requests.Session() as session:
        status = request_json(session, "GET", f"{origin}/api/user/status", headers=headers)
        account = status.get("data")
        if status.get("code") != 0 or not isinstance(account, dict):
            raise RuntimeError(
                f"账号验证失败：{short_message(status)}。请重新登录 {host} 并更新 GLADOS_COOKIE"
            )

        result = request_json(
            session,
            "POST",
            f"{origin}/api/user/checkin",
            headers=headers,
            json={"token": host},
        )

    message = short_message(result)
    lowered = message.lower()
    code = str(result.get("code"))
    if code == "4":
        detail = result.get("reason")
        if not detail and isinstance(result.get("data"), dict):
            detail = result["data"].get("reason")
        reason = f"，原因：{str(detail)[:50]}" if isinstance(detail, str) and detail else ""
        raise RuntimeError(
            f"GLaDOS 拒绝自动签到（code=4{reason}）：{message}。"
            "请确认 GLADOS_USER_AGENT 与登录浏览器一致；服务器也可能禁止自动请求"
        )
    if any(marker in lowered for marker in ERROR_MESSAGES):
        raise RuntimeError(f"签到被拒绝：{message}（code={code}）")

    if code in ("0", "1") and any(marker in lowered for marker in ALREADY_MESSAGES):
        outcome = "今日已签到"
    elif code == "0" and any(marker in lowered for marker in SUCCESS_MESSAGES):
        outcome = "签到成功"
    else:
        raise RuntimeError(f"签到未确认成功：{message}（code={code}）")

    print(f"{outcome}：{message}")
    print(f"账号：{masked_email(account.get('email'))}")
    left_days = account.get("leftDays")
    if left_days is not None:
        print(f"剩余服务天数：{left_days}")

    rewards = result.get("list")
    if outcome == "签到成功" and isinstance(rewards, list) and rewards and isinstance(rewards[0], dict):
        reward = rewards[0]
        print(f"奖励变化：{reward.get('change', '未知')}，积分余额：{reward.get('balance', '未知')}")
        if isinstance(reward.get("time"), (int, float)):
            when = datetime.fromtimestamp(reward["time"] / 1000, ZoneInfo("Asia/Shanghai"))
            print(f"奖励时间：{when:%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    try:
        check_in()
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"::error::GLaDOS 签到失败：{exc}", file=sys.stderr)
        sys.exit(1)
