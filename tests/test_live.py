import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.live import main
from orchestration.engine import Orchestrator
from orchestration.routing import FixedRouter
from orchestration.types import Completion, Model, ProviderError


class CountingProvider:
    def __init__(self, uncertain=False):
        self.calls = 0
        self.uncertain = uncertain

    def complete(self, model, task, messages):
        self.calls += 1
        if self.uncertain:
            raise ProviderError("Transport failure; billing unknown")
        return Completion("42", 10, 10, 1)


class LiveEvaluationTests(unittest.TestCase):
    def execute(self, provider, cap):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            data = root / "tasks.jsonl"
            output = root / "result.json"
            config.write_text(json.dumps({"limits": {"budget": "0.1"},
                                          "routing": {"type": "fixed"}, "models": []}))
            rows = [{"id": str(i), "prompt": "Return 42", "kind": "test",
                     "expected": "42", "max_output_tokens": 10} for i in range(5)]
            data.write_text("".join(json.dumps(r) + "\n" for r in rows))
            engine = Orchestrator([Model("m", "p", "stub", "0", "1")],
                                  {"p": provider}, FixedRouter("m"))
            argv = ["evaluate", "--config", str(config), "--dataset", str(data),
                    "--total-budget", cap, "--out", str(output), "--allow-network"]
            with patch("sys.argv", argv), patch("evaluation.live.build_engine", return_value=engine), contextlib.redirect_stdout(io.StringIO()):
                code = main()
            return code, json.loads(output.read_text())

    def test_total_budget_accounts_for_multiple_tasks(self):
        provider = CountingProvider()
        code, result = self.execute(provider, "0.000025")
        self.assertEqual(code, 0)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(result["spent"], "0.00002")
        self.assertEqual(result["successful_tasks"], 2)
        self.assertFalse(result["budget_overrun"])

    def test_uncertain_billing_stops_entire_evaluation(self):
        provider = CountingProvider(uncertain=True)
        code, result = self.execute(provider, "0.1")
        self.assertEqual(code, 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(result["evaluated_tasks"], 1)
        self.assertTrue(result["billing_uncertain"])

    def test_missing_opt_in_prevents_engine_creation(self):
        argv = ["evaluate", "--config", "unused", "--dataset", "unused", "--total-budget", "1"]
        with patch("sys.argv", argv), patch("evaluation.live.build_engine") as build, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)
            build.assert_not_called()
