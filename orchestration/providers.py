import ipaddress
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .types import Completion, Model, ProviderError, Task, estimate_tokens


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleProvider:
    """Non-streaming Chat Completions transport for explicitly configured endpoints.

    Compatible protocol does not mean every provider/model supports every option.
    Unknown billing on transport errors stops the run rather than retrying charges.
    """

    def __init__(self, base_url: str, api_key_env: str = "", timeout: float = 45):
        url = urllib.parse.urlparse(base_url)
        try:
            loopback = ipaddress.ip_address(url.hostname or "").is_loopback
        except ValueError:
            loopback = url.hostname == "localhost"
        if url.scheme != "https" and not (url.scheme == "http" and loopback):
            raise ValueError("Use HTTPS, or HTTP for a loopback inference server")
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Endpoint must not contain credentials, query parameters, or fragments")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.key = os.environ.get(api_key_env) if api_key_env else None
        if api_key_env and not self.key:
            raise ValueError(f"Missing environment variable: {api_key_env}")
        self.opener = urllib.request.build_opener(NoRedirect())

    def complete(self, model: Model, task: Task, messages: list[dict[str, str]]) -> Completion:
        payload = {"model": model.remote_model, "messages": messages,
                   "max_tokens": task.max_output_tokens, "temperature": 0,
                   "stream": False}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = urllib.request.Request(self.endpoint, json.dumps(payload).encode(), headers)
        start = time.monotonic()
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ProviderError("Provider response exceeds size limit")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ProviderError("Invalid response object; billing unknown")
            text = body["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise ProviderError("Provider did not return text content")
            usage = body.get("usage") or {}
            if not isinstance(usage, dict):
                raise ProviderError("Invalid usage object; billing unknown")
            estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
            input_tokens = usage.get("prompt_tokens", estimate_tokens(messages))
            output_tokens = usage.get("completion_tokens", len(text.encode("utf-8")))
            for count in (input_tokens, output_tokens):
                if type(count) is not int or count < 0:
                    raise ProviderError("Invalid token usage in provider response")
            return Completion(text, input_tokens, output_tokens,
                              (time.monotonic() - start) * 1000, estimated)
        except urllib.error.HTTPError as error:
            # Do not log response bodies: they can echo prompts or credentials.
            error.close()
            if error.code == 429:
                raise ProviderError("HTTP 429", retryable=True, billing_unknown=False) from None
            if error.code in (400, 401, 403, 404, 422):
                raise ProviderError(f"HTTP {error.code}", billing_unknown=False) from None
            raise ProviderError(f"HTTP {error.code}; billing unknown") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("Transport failure; billing unknown") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("Invalid provider response; billing unknown") from None
