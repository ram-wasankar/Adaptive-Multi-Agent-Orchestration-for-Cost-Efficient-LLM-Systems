import hashlib
import json
from dataclasses import replace
from pathlib import Path

from orchestration.engine import Orchestrator
from orchestration.routing import CalibratedRouter, CascadeRouter
from orchestration.types import Verdict
from .fixtures import ReplayProvider, as_task, calibration, make_dataset, models


class FirstChoiceOnly:
    def __init__(self, router):
        self.router = router

    def order(self, task, pool, input_tokens):
        return self.router.order(task, pool, input_tokens)[:1]


def imperfect_validator(row):
    def check(text):
        correct = text.strip() == row["expected"]
        digest = hashlib.sha256((row["id"] + ":" + text).encode()).digest()
        uniform = int.from_bytes(digest[:8], "big") / 2**64
        passed = uniform >= 0.05 if correct else uniform < 0.10
        return Verdict(passed, "scripted imperfect verifier")
    return check


def main():
    train = make_dataset("calibration", 80, 20261026)
    rows = make_dataset("test", 100, 20261027)
    observations = calibration(train)
    provider = ReplayProvider(rows)
    scenarios = [
        ("calibrated_no_escalation", FirstChoiceOnly(CalibratedRouter(observations, "large")), "0.05", False),
        ("calibrated_target_095", CalibratedRouter(observations, "large", 0.95), "0.05", False),
        ("calibrated_imperfect_verifier", CalibratedRouter(observations, "large"), "0.05", True),
        ("cascade_imperfect_verifier", CascadeRouter(), "0.05", True),
    ]
    for budget in ("0.00002", "0.0001", "0.001"):
        scenarios.append(("budget_" + budget, CalibratedRouter(observations, "large"), budget, False))
    reports, traces = {}, []
    for name, router, budget, noisy in scenarios:
        accepted = correct = calls = false_accepts = denied = 0
        cost = 0.0
        for row in rows:
            task = as_task(row)
            if noisy:
                task = replace(task, validate=imperfect_validator(row))
            run = Orchestrator(models(), {"replay_a": provider, "replay_b": provider},
                               router, budget=budget, retry_backoff=0).run([task])
            passed = run.success
            truly_correct = passed and run.tasks[0].output == row["expected"]
            accepted += passed
            correct += truly_correct
            false_accepts += passed and not truly_correct
            calls += sum(a.status in ("accepted", "rejected") for a in run.attempts)
            denied += run.tasks[0].status == "budget_exhausted"
            cost += float(run.spent)
            traces.append({"scenario": name, "task_id": row["id"],
                           "ground_truth_correct": truly_correct, **run.to_dict()})
        reports[name] = {"tasks": len(rows), "accepted": accepted, "correct": correct,
                         "false_accepts": false_accepts, "calls": calls,
                         "budget_exhausted": denied, "simulated_cost": round(cost, 9)}
    output = Path("results/offline")
    output.mkdir(parents=True, exist_ok=True)
    (output / "sensitivity.json").write_text(json.dumps({
        "experiment": "synthetic controls, not live-model performance",
        "imperfect_verifier": {"false_positive_probability": 0.10, "false_negative_probability": 0.05,
                               "note": "deterministic per answer; not calibrated from real verifiers"},
        "scenarios": reports}, indent=2) + "\n")
    (output / "sensitivity_traces.jsonl").write_text("".join(json.dumps(row) + "\n" for row in traces))
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
