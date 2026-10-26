import argparse
import csv
import hashlib
import json
import math
import platform
import random
from pathlib import Path

from orchestration.engine import Orchestrator
from orchestration.routing import CalibratedRouter, CascadeRouter, FixedRouter
from .fixtures import LATENCY_MS, PROBABILITIES, ReplayProvider, as_task, calibration, digest_rows, make_dataset, models


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def wilson(successes, count):
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [round(center - half, 6), round(center + half, 6)]


def summarize(records):
    successes = sum(row["success"] for row in records)
    total_cost = sum(float(row["spent"]) for row in records)
    total_calls = sum(row["calls"] for row in records)
    return {"tasks": len(records), "successful_tasks": successes,
            "success_rate": successes / len(records),
            "success_rate_wilson_95": wilson(successes, len(records)),
            "simulated_cost": round(total_cost, 9),
            "simulated_cost_per_success": round(total_cost / successes, 9) if successes else None,
            "calls": total_calls, "calls_per_task": total_calls / len(records),
            "escalated_tasks": sum(row["calls"] > 1 for row in records),
            "input_tokens": sum(row["input_tokens"] for row in records),
            "output_tokens": sum(row["output_tokens"] for row in records),
            "simulated_p50_ms": percentile([r["simulated_ms"] for r in records], 0.50),
            "simulated_p95_ms": percentile([r["simulated_ms"] for r in records], 0.95),
            "measured_replay_wall_ms": sum(row["wall_ms"] for row in records)}


def paired_savings_interval(baseline, adaptive, seed=20261026, repeats=2000):
    rng = random.Random(seed)
    values = []
    n = len(baseline)
    for _ in range(repeats):
        indices = [rng.randrange(n) for _ in range(n)]
        denominator = sum(float(baseline[i]["spent"]) for i in indices)
        numerator = sum(float(adaptive[i]["spent"]) for i in indices)
        values.append(1 - numerator / denominator)
    return [percentile(values, 0.025), percentile(values, 0.975)]


def source_hash():
    digest = hashlib.sha256()
    for directory in (Path("orchestration"), Path("evaluation")):
        for path in sorted(directory.glob("*.py")):
            digest.update(str(path).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluate(output: Path, per_family=100, seed=20261026):
    output.mkdir(parents=True, exist_ok=True)
    train = make_dataset("calibration", 80, seed)
    test = make_dataset("test", per_family, seed + 1)
    observations = calibration(train)
    provider = ReplayProvider(test)
    policies = {"always_small": FixedRouter("small"), "always_large": FixedRouter("large"),
                "cheap_first_cascade": CascadeRouter(),
                "calibrated_routing": CalibratedRouter(observations, "large")}
    all_records, summaries = {}, {}
    for name, router in policies.items():
        records = []
        for row in test:
            run = Orchestrator(models(), {"replay_a": provider, "replay_b": provider}, router,
                               budget="0.05", retry_backoff=0).run([as_task(row)])
            record = {"task_id": row["id"], "kind": row["kind"], "policy": name,
                      "success": run.success, "spent": str(run.spent),
                      "calls": len(run.attempts),
                      "simulated_ms": sum(a.provider_latency_ms for a in run.attempts),
                      "input_tokens": sum(a.input_tokens for a in run.attempts),
                      "output_tokens": sum(a.output_tokens for a in run.attempts),
                      "wall_ms": run.wall_ms, "attempts": run.to_dict()["attempts"]}
            records.append(record)
        all_records[name] = records
        summaries[name] = summarize(records)
    baseline = summaries["always_large"]["simulated_cost"]
    adaptive = summaries["calibrated_routing"]["simulated_cost"]
    by_family = {policy: {kind: summarize([r for r in rows if r["kind"] == kind])
                         for kind in ("extraction", "arithmetic", "reasoning")}
                 for policy, rows in all_records.items()}
    report = {"experiment": "synthetic replay; no live LLM calls", "seed": seed,
              "calibration_tasks": len(train), "test_tasks": len(test),
              "train_sha256": digest_rows(train), "test_sha256": digest_rows(test),
              "source_sha256": source_hash(), "python": platform.python_version(),
              "assumptions": {"scripted_success_probabilities": PROBABILITIES,
                              "modeled_latency_ms": LATENCY_MS,
                              "rates": {m.name: {"input_per_million": str(m.input_per_million),
                                                 "output_per_million": str(m.output_per_million)}
                                        for m in models()},
                              "validator": "exact-match oracle; zero modeled external cost",
                              "quality_target": 0.85, "routing": "frozen calibration; no test-set updates"},
              "policies": summaries, "by_family": by_family,
              "comparison": {"simulated_savings_vs_large": 1 - adaptive / baseline,
                             "paired_bootstrap_savings_95": paired_savings_interval(
                                 all_records["always_large"], all_records["calibrated_routing"])}}
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "calibration.json").write_text(json.dumps(observations, indent=2) + "\n")
    for name, rows in (("calibration", train), ("test", test)):
        (output / f"{name}_fixtures.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    with (output / "traces.jsonl").open("w") as handle:
        for rows in all_records.values():
            for row in rows:
                handle.write(json.dumps(row) + "\n")
    with (output / "summary.csv").open("w", newline="") as handle:
        keys = [key for key in next(iter(summaries.values())) if key != "success_rate_wilson_95"]
        writer = csv.DictWriter(handle, fieldnames=["policy", *keys])
        writer.writeheader()
        for policy, summary in summaries.items():
            writer.writerow({"policy": policy, **{key: summary[key] for key in keys}})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("results/offline"))
    parser.add_argument("--per-family", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261026)
    args = parser.parse_args()
    if args.per_family < 1:
        parser.error("per-family must be positive")
    result = evaluate(args.out, args.per_family, args.seed)
    print(json.dumps({"experiment": result["experiment"], "policies": result["policies"]}, indent=2))


if __name__ == "__main__":
    main()
