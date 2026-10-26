import unittest
from decimal import Decimal

from orchestration.context import ContextOverflow, build_messages
from orchestration.engine import Orchestrator, topological_order
from orchestration.routing import CalibratedRouter, CascadeRouter, FixedRouter
from orchestration.types import Completion, Model, ProviderError, Task, Verdict
from orchestration.validation import exact_match, json_keys


class Stub:
    def __init__(self, replies):
        self.replies, self.calls, self.messages = list(replies), [], []

    def complete(self, model, task, messages):
        self.calls.append((task.id, model.name))
        self.messages.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, Completion):
            return reply
        return Completion(reply, 20, 5, 10)


def pool():
    return [Model("small", "a", "small", "1", "2"),
            Model("large", "b", "large", "10", "20")]


def task(name="one", deps=()):
    return Task(name, "Return yes", "test", exact_match("yes"), deps, 16)


def engine(provider, router=None, **kwargs):
    return Orchestrator(pool(), {"a": provider, "b": provider}, router or CascadeRouter(),
                        retry_backoff=0, **kwargs)


class EngineTests(unittest.TestCase):
    def test_stops_after_first_verified_response(self):
        provider = Stub(["yes"])
        result = engine(provider).run([task()])
        self.assertTrue(result.success)
        self.assertEqual(provider.calls, [("one", "small")])
        self.assertEqual(result.spent, Decimal("0.00003"))

    def test_cross_provider_escalation_accounts_for_both_calls(self):
        provider = Stub(["no", "yes"])
        result = engine(provider).run([task()])
        self.assertTrue(result.success)
        self.assertEqual([a.provider for a in result.attempts], ["a", "b"])
        self.assertEqual(result.spent, Decimal("0.00033"))

    def test_budget_denial_performs_no_call(self):
        provider = Stub([])
        result = engine(provider, budget="0").run([task()])
        self.assertEqual(result.tasks[0].status, "budget_exhausted")
        self.assertEqual(provider.calls, [])

    def test_actual_usage_overrun_halts_downstream(self):
        provider = Stub([Completion("yes", 1_000_000, 5, 1)])
        result = engine(provider, budget="0.01").run([task(), task("two", ("one",))])
        self.assertEqual(result.tasks[0].status, "budget_overrun")
        self.assertEqual(result.tasks[1].status, "budget_halted")
        self.assertGreater(result.spent, result.budget)
        self.assertEqual(len(provider.calls), 1)

    def test_unknown_billing_does_not_retry_or_fail_over(self):
        provider = Stub([ProviderError("timeout")])
        result = engine(provider).run([task(), task("other")])
        self.assertTrue(result.billing_uncertain)
        self.assertGreater(result.spent, 0)
        self.assertEqual(result.tasks[1].status, "budget_halted")
        self.assertEqual(len(provider.calls), 1)

    def test_rate_limit_retries_are_bounded(self):
        error = ProviderError("rate limit", retryable=True, billing_unknown=False)
        provider = Stub([error, error, "yes"])
        result = engine(provider, retries=1).run([task()])
        self.assertTrue(result.success)
        self.assertEqual([name for _, name in provider.calls], ["small", "small", "large"])
        self.assertEqual(result.spent, Decimal("0.0003"))

    def test_failed_dependency_blocks_child_but_not_independent_task(self):
        provider = Stub(["no", "yes"])
        result = engine(provider, FixedRouter("small")).run(
            [task(), task("child", ("one",)), task("independent")])
        statuses = {row.task_id: row.status for row in result.tasks}
        self.assertEqual(statuses["child"], "dependency_failed")
        self.assertEqual(statuses["independent"], "success")
        self.assertEqual(len(provider.calls), 2)

    def test_outputs_are_handed_to_child(self):
        provider = Stub(["yes", "yes"])
        result = engine(provider).run([task("child", ("one",)), task()])
        self.assertTrue(result.success)
        self.assertIn('"task_id":"one"', provider.messages[1][1]["content"])
        self.assertIn('"output":"yes"', provider.messages[1][1]["content"])

    def test_context_overflow_never_silently_truncates(self):
        provider = Stub(["yes"])
        result = engine(provider, context_chars=0).run([task(), task("child", ("one",))])
        self.assertEqual(result.tasks[1].status, "context_limit")
        self.assertEqual(len(provider.calls), 1)

    def test_context_window_skips_model(self):
        provider = Stub([])
        tiny = Model("tiny", "a", "tiny", 1, 1, context_window=1)
        result = Orchestrator([tiny], {"a": provider}, CascadeRouter()).run([task()])
        self.assertEqual(result.tasks[0].status, "context_window")
        self.assertEqual(provider.calls, [])

    def test_validator_exception_stops_task(self):
        def broken(_):
            raise RuntimeError("private validator detail")
        provider = Stub(["yes"])
        result = engine(provider).run([Task("x", "q", "test", broken)])
        self.assertEqual(result.tasks[0].status, "validator_error")
        self.assertNotIn("private validator detail", str(result.to_dict()))

    def test_trace_excludes_output_by_default(self):
        result = engine(Stub(["yes"])).run([task()])
        self.assertNotIn("output", result.to_dict()["tasks"][0])
        self.assertEqual(result.to_dict(True)["tasks"][0]["output"], "yes")
        self.assertEqual(len(result.attempts[0].output_sha256), 64)

    def test_reusing_engine_does_not_reuse_budget_or_context(self):
        instance = engine(Stub(["yes", "yes"]))
        first, second = instance.run([task()]), instance.run([task()])
        self.assertEqual(first.spent, second.spent)
        self.assertEqual(len(second.attempts), 1)


class GraphAndRoutingTests(unittest.TestCase):
    def test_cycles_unknown_edges_and_duplicates_rejected(self):
        cases = [[task("a", ("b",)), task("b", ("a",))],
                 [task("a", ("missing",))], [task(), task()], []]
        for tasks in cases:
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                topological_order(tasks)

    def test_selective_context_excludes_unrelated_artifact(self):
        t = task("child", ("one",))
        messages, _ = build_messages(t, {"one": "relevant", "other": "PRIVATE"}, 1000)
        self.assertIn("relevant", str(messages))
        self.assertNotIn("PRIVATE", str(messages))

    def test_calibrated_router_selects_cheapest_eligible(self):
        router = CalibratedRouter({"test": {"small": (98, 100), "large": (99, 100)}}, "large")
        self.assertEqual(router.order(task(), pool(), 100)[0].name, "small")

    def test_low_quality_routes_to_large(self):
        router = CalibratedRouter({"test": {"small": (20, 100), "large": (99, 100)}}, "large")
        self.assertEqual(router.order(task(), pool(), 100)[0].name, "large")

    def test_unseen_family_uses_explicit_fallback(self):
        router = CalibratedRouter({}, "large")
        self.assertEqual([m.name for m in router.order(task(), pool(), 100)], ["large"])

    def test_invalid_prices_and_calibration_rejected(self):
        for value in ("-1", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Model("m", "p", "r", value, "1")
        with self.assertRaises(ValueError):
            CalibratedRouter({"test": {"small": (10, 2)}}, "large")

    def test_shape_validation_is_not_semantic_validation(self):
        validator = json_keys(["answer"])
        self.assertTrue(validator('{"answer":"wrong"}').passed)
        self.assertFalse(validator("not json").passed)
        self.assertFalse(validator("[]").passed)


if __name__ == "__main__":
    unittest.main()
