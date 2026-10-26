import unittest

from evaluation.fixtures import as_task, calibration, digest_rows, make_dataset, models, ReplayProvider
from evaluation.run import paired_savings_interval, summarize
from orchestration.engine import Orchestrator
from orchestration.routing import CalibratedRouter


class EvaluationTests(unittest.TestCase):
    def test_fixtures_reproduce_and_splits_do_not_overlap(self):
        a, b = make_dataset("calibration", 10, 7), make_dataset("test", 10, 8)
        self.assertEqual(digest_rows(a), digest_rows(make_dataset("calibration", 10, 7)))
        self.assertFalse({row["id"] for row in a} & {row["id"] for row in b})

    def test_calibration_stays_frozen_during_test(self):
        train, test = make_dataset("calibration", 10, 7), make_dataset("test", 5, 8)
        observations = calibration(train)
        before = repr(observations)
        provider = ReplayProvider(test)
        router = CalibratedRouter(observations, "large")
        for row in test:
            Orchestrator(models(), {"replay_a": provider, "replay_b": provider}, router).run([as_task(row)])
        self.assertEqual(repr(observations), before)

    def test_identical_costs_have_zero_paired_savings(self):
        rows = [{"spent": "1"}, {"spent": "2"}, {"spent": "3"}]
        self.assertEqual(paired_savings_interval(rows, rows, repeats=50), [0.0, 0.0])

    def test_zero_success_cost_metric_is_undefined(self):
        row = {"success": False, "spent": "1", "calls": 1, "input_tokens": 1,
               "output_tokens": 1, "simulated_ms": 1, "wall_ms": 1}
        self.assertIsNone(summarize([row])["simulated_cost_per_success"])


if __name__ == "__main__":
    unittest.main()
