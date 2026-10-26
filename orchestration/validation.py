import json

from .types import Verdict


def exact_match(expected: str):
    def check(text: str) -> Verdict:
        passed = text.strip() == expected.strip()
        return Verdict(passed, "exact match" if passed else "answer mismatch")
    return check


def json_keys(required: list[str]):
    """Checks output shape only. It does not establish factual correctness."""
    def check(text: str) -> Verdict:
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            return Verdict(False, "invalid JSON")
        passed = isinstance(value, dict) and all(key in value for key in required)
        return Verdict(passed, "required keys present" if passed else "missing required keys")
    return check
