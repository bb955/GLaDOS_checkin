import hashlib
import os
import unittest
from unittest.mock import patch

import checkin


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise checkin.requests.HTTPError("simulated error")

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def close(self):
        return None


VALID_STATUS = {"code": 0, "data": {"leftDays": 365}}
SETTINGS = checkin.Settings("gld:sess=x; gld:sess.sig=y", "Actual Browser UA")


class ConfigTests(unittest.TestCase):
    def test_missing_cookie(self):
        with patch.dict(os.environ, {"GLADOS_COOKIE": ""}):
            with self.assertRaisesRegex(checkin.CheckinError, "GLADOS_COOKIE"):
                checkin.Settings.from_env()

    def test_missing_cookie_signature(self):
        with patch.dict(os.environ, {"GLADOS_COOKIE": "gld:sess=test"}):
            with self.assertRaisesRegex(checkin.CheckinError, "gld:sess.sig"):
                checkin.Settings.from_env()

    def test_cookie_line_break_rejected(self):
        with patch.dict(os.environ, {"GLADOS_COOKIE": "gld:sess=x\ngld:sess.sig=y"}):
            with self.assertRaisesRegex(checkin.CheckinError, "换行"):
                checkin.Settings.from_env()

    def test_user_agent_from_env(self):
        with patch.dict(os.environ, {"GLADOS_COOKIE": SETTINGS.cookie, "GLADOS_USER_AGENT": "Firefox Example"}):
            self.assertEqual(checkin.Settings.from_env().user_agent, "Firefox Example")

    def test_ua_line_break_rejected(self):
        with patch.dict(os.environ, {"GLADOS_COOKIE": SETTINGS.cookie, "GLADOS_USER_AGENT": "UA\nX: y"}):
            with self.assertRaisesRegex(checkin.CheckinError, "换行"):
                checkin.Settings.from_env()


class ClassifyTests(unittest.TestCase):
    def test_success(self):
        self.assertEqual(checkin.classify_checkin({"code": 0, "message": "Checkin! Got 1 Point"}), "签到成功")

    def test_repeat(self):
        self.assertEqual(checkin.classify_checkin({"code": 1, "message": "Checkin Repeats! Please Try Tomorrow"}), "今日已签到")

    def test_code_four(self):
        with self.assertRaisesRegex(checkin.CheckinError, "code=4"):
            checkin.classify_checkin({"code": 4, "message": "Automated check-in detected"})

    def test_code_four_message_explains_no_auto_retry(self):
        with self.assertRaisesRegex(checkin.CheckinError, "不会自动重试"):
            checkin.classify_checkin({
                "code": 4,
                "message": "Automated check-in detected. Please sign in again to continue.",
            })

    def test_code_four_device_mismatch_reason_is_actionable(self):
        with self.assertRaisesRegex(checkin.CheckinError, "device-mismatch"):
            checkin.classify_checkin({
                "code": 4, "reason": "device-mismatch",
                "message": "Automated check-in detected",
            })

    def test_code_four_does_not_log_untrusted_device_payload(self):
        with self.assertRaises(checkin.CheckinError) as caught:
            checkin.classify_checkin({
                "code": 4, "reason": "unrecognized",
                "loginDevice": "private-device-identifier",
                "message": "Automated check-in detected",
            })
        self.assertNotIn("private-device-identifier", str(caught.exception))
        self.assertNotIn("unrecognized", str(caught.exception))

    def test_code_zero_unknown(self):
        with self.assertRaisesRegex(checkin.CheckinError, "没有确认"):
            checkin.classify_checkin({"code": 0, "message": "unrecognized"})

    def test_code_one_unknown(self):
        with self.assertRaises(checkin.CheckinError):
            checkin.classify_checkin({"code": 1, "message": "no"})

    def test_reject_even_code_zero(self):
        with self.assertRaisesRegex(checkin.CheckinError, "拒绝"):
            checkin.classify_checkin({"code": 0, "message": "Please sign in again"})


class NetworkTests(unittest.TestCase):
    def test_status_only_never_posts(self):
        session = FakeSession(FakeResponse(VALID_STATUS))
        self.assertIn("Cookie 有效", checkin.run("status", checkin.Settings(SETTINGS.cookie, None), session))
        self.assertEqual([c[0] for c in session.calls], ["GET"])

    def test_browser_client_hints_match_actual_chrome_user_agent(self):
        settings = checkin.Settings(
            SETTINGS.cookie,
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/156.0.0.0 Safari/537.36",
        )
        headers = checkin.build_headers(settings)
        self.assertEqual(headers["User-Agent"], settings.user_agent)
        self.assertIn('"Google Chrome";v="156"', headers["Sec-CH-UA"])
        self.assertEqual(headers["Sec-CH-UA-Mobile"], "?0")
        self.assertEqual(headers["Sec-CH-UA-Platform"], '"macOS"')
        self.assertEqual(headers["Sec-Fetch-Site"], "same-origin")
        self.assertEqual(headers["Accept"], "application/json, text/plain, */*")

    def test_checkin_success_uses_fresh_challenge_and_proof(self):
        nonce = "fresh-nonce"
        session = FakeSession(
            FakeResponse(VALID_STATUS),
            FakeResponse({"code": 0, "nonce": nonce, "ttl": 300000}),
            FakeResponse({"code": 0, "message": "Checkin! Got 1 Point"}),
        )
        with patch("checkin.time.sleep") as sleep, patch(
            "checkin.time.monotonic", side_effect=[100.0, 102.0]
        ):
            self.assertEqual(checkin.run("checkin", SETTINGS, session), "签到成功")
        self.assertEqual([c[0] for c in session.calls], ["GET", "GET", "POST"])
        self.assertTrue(session.calls[1][1].endswith("/api/user/checkin/challenge"))
        expected_proof = hashlib.sha256(
            (nonce + ".glados-observe-v1").encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            session.calls[2][2]["json"],
            {"token": "glados.cloud", "nonce": nonce, "proof": expected_proof},
        )
        self.assertEqual(session.calls[2][1], checkin.CHECKIN_URL)
        self.assertEqual(session.calls[2][2]["headers"]["User-Agent"], "Actual Browser UA")
        sleep.assert_called_once_with(checkin.CHECKIN_CHALLENGE_DELAY)

    def test_checkin_challenge_failure_never_posts(self):
        session = FakeSession(
            FakeResponse(VALID_STATUS),
            FakeResponse({"code": 5, "message": "challenge required"}),
        )
        with self.assertRaisesRegex(checkin.CheckinError, "获取一次性签到验证失败"):
            checkin.run("checkin", SETTINGS, session)
        self.assertEqual([c[0] for c in session.calls], ["GET", "GET"])

    def test_checkin_challenge_missing_nonce_never_posts(self):
        session = FakeSession(
            FakeResponse(VALID_STATUS),
            FakeResponse({"code": 0, "ttl": 300000}),
        )
        with self.assertRaisesRegex(checkin.CheckinError, "获取一次性签到验证失败"):
            checkin.run("checkin", SETTINGS, session)
        self.assertEqual([c[0] for c in session.calls], ["GET", "GET"])

    def test_checkin_challenge_expired_never_posts(self):
        session = FakeSession(
            FakeResponse(VALID_STATUS),
            FakeResponse({"code": 0, "nonce": "fresh-nonce", "ttl": 300000}),
        )
        with patch("checkin.time.sleep"), patch(
            "checkin.time.monotonic", side_effect=[100.0, 401.0]
        ):
            with self.assertRaisesRegex(checkin.CheckinError, "验证已过期"):
                checkin.run("checkin", SETTINGS, session)
        self.assertEqual([c[0] for c in session.calls], ["GET", "GET"])

    def test_observation_logged_is_success(self):
        self.assertEqual(
            checkin.classify_checkin({
                "code": 1,
                "message": "Today's observation logged. Return tomorrow for more points.",
            }),
            "签到成功",
        )

    def test_code_five_known_success_message_is_success(self):
        self.assertEqual(
            checkin.classify_checkin({"code": 5, "message": "Checkin! Got 5 Points"}),
            "签到成功",
        )

    def test_code_five_known_repeat_message_is_already_done(self):
        self.assertEqual(
            checkin.classify_checkin({
                "code": 5,
                "message": "Checkin Repeats! Please Try Tomorrow",
            }),
            "今日已签到",
        )

    def test_unknown_response_reports_only_allowlisted_tags(self):
        with self.assertRaises(checkin.CheckinError) as caught:
            checkin.classify_checkin({
                "code": 5,
                "message": "Invalid proof for nonce challenge; account private@example.com",
            })
        message = str(caught.exception)
        self.assertIn("响应特征=challenge,nonce,proof", message)
        self.assertNotIn("private@example.com", message)
        self.assertNotIn("Invalid proof", message)

    def test_code_five_unknown_message_remains_failure(self):
        with self.assertRaisesRegex(checkin.CheckinError, "code=5"):
            checkin.classify_checkin({"code": 5, "message": "unknown response"})

    def test_checkin_repeats_is_already_done(self):
        self.assertEqual(
            checkin.classify_checkin({
                "code": 1,
                "message": "Checkin Repeats! Please Try Tomorrow",
            }),
            "今日已签到",
        )

    def test_missing_ua_blocks_before_network(self):
        session = FakeSession()
        with self.assertRaisesRegex(checkin.CheckinError, "GLADOS_USER_AGENT"):
            checkin.run("checkin", checkin.Settings(SETTINGS.cookie, None), session)
        self.assertEqual(session.calls, [])

    def test_invalid_login_never_posts(self):
        session = FakeSession(FakeResponse({"code": 1, "message": "not logged in"}))
        with self.assertRaisesRegex(checkin.CheckinError, "Cookie"):
            checkin.run("checkin", SETTINGS, session)
        self.assertEqual([c[0] for c in session.calls], ["GET"])

    def test_redirect_not_followed(self):
        session = FakeSession(FakeResponse({}, status_code=302))
        with self.assertRaisesRegex(checkin.CheckinError, "重定向"):
            checkin.run("status", SETTINGS, session)
        self.assertFalse(session.calls[0][2]["allow_redirects"])

    def test_http_error(self):
        session = FakeSession(FakeResponse({}, status_code=503))
        with self.assertRaisesRegex(checkin.CheckinError, "请求失败"):
            checkin.run("status", SETTINGS, session)

    def test_reject_non_json_object(self):
        session = FakeSession(FakeResponse([]))
        with self.assertRaisesRegex(checkin.CheckinError, "JSON 对象"):
            checkin.run("status", SETTINGS, session)


if __name__ == "__main__":
    unittest.main()
