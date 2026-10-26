import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from orchestration.providers import OpenAICompatibleProvider
from orchestration.types import Model, ProviderError, Task
from orchestration.validation import exact_match


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = {"choices": [{"message": {"content": "yes"}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        self.status = 200
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append((self.path, json.loads(body)))
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                if owner.status == 302:
                    self.send_header("Location", "/do-not-follow")
                self.end_headers()
                self.wfile.write(json.dumps(owner.response).encode())

            def log_message(self, *_):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.provider = OpenAICompatibleProvider(f"http://127.0.0.1:{self.server.server_port}/v1")
        self.model = Model("m", "p", "served-model", "1", "2")
        self.task = Task("id", "question", "test", exact_match("SECRET EXPECTED"))
        self.messages = [{"role": "user", "content": "question"}]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self):
        return self.provider.complete(self.model, self.task, self.messages)

    def test_wire_format_and_no_answer_leak(self):
        reply = self.call()
        path, body = self.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["model"], "served-model")
        self.assertNotIn("SECRET EXPECTED", json.dumps(body))
        self.assertFalse(reply.usage_estimated)
        self.assertEqual(reply.input_tokens, 10)

    def test_missing_usage_is_flagged_as_estimated(self):
        del self.response["usage"]
        self.assertTrue(self.call().usage_estimated)

    def test_invalid_response_has_uncertain_billing(self):
        self.response = {"private": "do not leak"}
        with self.assertRaises(ProviderError) as caught:
            self.call()
        self.assertTrue(caught.exception.billing_unknown)
        self.assertNotIn("do not leak", str(caught.exception))

    def test_429_is_retryable_and_not_charged(self):
        self.status = 429
        with self.assertRaises(ProviderError) as caught:
            self.call()
        self.assertTrue(caught.exception.retryable)
        self.assertFalse(caught.exception.billing_unknown)

    def test_malformed_usage_preserves_billing_uncertainty(self):
        self.response["usage"] = [10, 2]
        with self.assertRaises(ProviderError) as caught:
            self.call()
        self.assertTrue(caught.exception.billing_unknown)

    def test_401_is_not_retried(self):
        self.status = 401
        with self.assertRaises(ProviderError) as caught:
            self.call()
        self.assertFalse(caught.exception.retryable)
        self.assertFalse(caught.exception.billing_unknown)

    def test_redirects_are_not_followed(self):
        self.status = 302
        with self.assertRaises(ProviderError):
            self.call()
        self.assertEqual(len(self.requests), 1)

    def test_timeout_is_not_silently_retried(self):
        with patch.object(self.provider.opener, "open", side_effect=TimeoutError()):
            with self.assertRaises(ProviderError) as caught:
                self.call()
        self.assertTrue(caught.exception.billing_unknown)

    def test_insecure_remote_and_embedded_credentials_rejected(self):
        for url in ("http://example.com/v1", "https://user:pass@example.com/v1",
                    "https://example.com/v1?secret=value"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OpenAICompatibleProvider(url)


if __name__ == "__main__":
    unittest.main()
