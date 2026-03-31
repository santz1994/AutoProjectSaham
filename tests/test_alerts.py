import unittest
from unittest.mock import Mock, patch

from src.alerts import webhook


class WebhookTests(unittest.TestCase):
    @patch("src.alerts.webhook.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        ok = webhook.send_alert_webhook(
            "http://example.com/hook", {"m": "x"}, retries=1, backoff=0, jitter=0
        )
        self.assertTrue(ok)
        mock_post.assert_called_once()

    @patch("src.alerts.webhook.requests.post")
    def test_send_retry_then_success(self, mock_post):
        m1 = Mock(status_code=500)
        m2 = Mock(status_code=201)
        mock_post.side_effect = [m1, m2]
        ok = webhook.send_alert_webhook(
            "http://ex", {"a": 1}, retries=3, backoff=0, jitter=0
        )
        self.assertTrue(ok)
        self.assertEqual(mock_post.call_count, 2)

    @patch("src.alerts.webhook.requests.post")
    def test_send_all_fail(self, mock_post):
        mock_post.return_value = Mock(status_code=500)
        ok = webhook.send_alert_webhook(
            "http://ex", {"a": 1}, retries=2, backoff=0, jitter=0
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
