import unittest

from browser_checkin import BUTTON_NAME, classify_browser_response
from checkin import CheckinError


class BrowserResponseTests(unittest.TestCase):
    def test_button_name_matches_english_and_chinese(self):
        self.assertRegex("Check in", BUTTON_NAME)
        self.assertRegex("Check-in", BUTTON_NAME)
        self.assertRegex("签到", BUTTON_NAME)

    def test_explicit_success(self):
        self.assertEqual(
            classify_browser_response({"code": 0, "message": "Checkin!"}),
            "签到成功",
        )

    def test_explicit_already_checked_in(self):
        self.assertEqual(
            classify_browser_response({"code": 5, "message": "Checkin repeats"}),
            "今日已签到",
        )

    def test_unknown_response_fails_closed(self):
        with self.assertRaises(CheckinError):
            classify_browser_response({"code": 5, "message": "unknown"})

    def test_turnstile_rejection_is_not_success(self):
        with self.assertRaises(CheckinError):
            classify_browser_response({
                "code": 5,
                "reason": "turnstile",
                "message": "Cloudflare verification failed",
            })


if __name__ == "__main__":
    unittest.main()
