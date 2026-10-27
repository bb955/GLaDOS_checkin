import os
import unittest
from unittest.mock import patch

import glados


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, status, checkin):
        self.responses = [FakeResponse(status), FakeResponse(checkin)]
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class CheckinTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "GLADOS_COOKIE": "gld:sess=test; gld:sess.sig=test",
            "GLADOS_ORIGIN": "https://glados.cloud",
            "GLADOS_UA": "Test Browser",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_session(self, response, status=None):
        session = FakeSession(status or {"code": 0, "data": {"email": "user@example.com", "leftDays": 10}}, response)
        self.session_patch = patch.object(glados.requests, "Session", return_value=session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        return session

    def test_missing_cookie_fails(self):
        os.environ["GLADOS_COOKIE"] = ""
        with self.assertRaisesRegex(ValueError, "GLADOS_COOKIE"):
            glados.check_in()

    def test_success_uses_matching_domain_token(self):
        session = self.fake_session({"code": 0, "message": "Checkin! Got 1 Point"})
        glados.check_in()
        method, url, args = session.calls[1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://glados.cloud/api/user/checkin")
        self.assertEqual(args["json"], {"token": "glados.cloud"})
        self.assertEqual(args["headers"]["user-agent"], "Test Browser")

    def test_already_checked_in_is_success(self):
        self.fake_session({"code": 1, "message": "Checkin Repeats! Please Try Tomorrow"})
        glados.check_in()

    def test_rejected_checkin_fails_even_with_zero_code(self):
        self.fake_session({"code": 0, "message": "please checkin via https://glados.cloud"})
        with self.assertRaisesRegex(RuntimeError, "签到被拒绝"):
            glados.check_in()

    def test_unknown_response_fails(self):
        self.fake_session({"code": 9, "message": "unknown error"})
        with self.assertRaisesRegex(RuntimeError, "未确认成功"):
            glados.check_in()

    def test_invalid_cookie_fails_before_post(self):
        session = self.fake_session({}, status={"code": 1, "message": "没有权限"})
        with self.assertRaisesRegex(RuntimeError, "账号验证失败"):
            glados.check_in()
        self.assertEqual(len(session.calls), 1)

    def test_rejects_unapproved_origin(self):
        os.environ["GLADOS_ORIGIN"] = "https://not-glados.example"
        with self.assertRaisesRegex(ValueError, "GLADOS_ORIGIN"):
            glados.check_in()

    def test_empty_actions_variable_uses_default_domain(self):
        os.environ["GLADOS_ORIGIN"] = ""
        self.assertEqual(glados.get_origin(), "https://glados.cloud")


if __name__ == "__main__":
    unittest.main()
