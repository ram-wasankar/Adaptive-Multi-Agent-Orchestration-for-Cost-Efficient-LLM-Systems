import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from orchestration.cli import build_engine
from orchestration.types import Task, money
from orchestration.validation import exact_match


def main():
    parser = argparse.ArgumentParser(description="Evaluate one configured policy on labeled live tasks")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--total-budget", required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("results/live/evaluation.json"))
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("Use --allow-network to authorize requests to configured model endpoints")
    config = json.loads(Path(args.config).read_text())
    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    if not rows or len({r["id"] for r in rows}) != len(rows):
        parser.error("Dataset must be non-empty with unique IDs")
    cap, spent = money(args.total_budget), Decimal(0)
    per_task = money(config["limits"]["budget"])
    engine = build_engine(config)
    records = []
    for row in rows:
        if spent >= cap:
            break
        engine.budget = min(per_task, cap - spent)
        task = Task(row["id"], row["prompt"], row["kind"], exact_match(str(row["expected"])),
                    max_output_tokens=row.get("max_output_tokens", 128))
        run = engine.run([task])
        spent += run.spent
        records.append(run.to_dict())
        if run.billing_uncertain or spent > cap:
            break
    successes = sum(r["success"] for r in records)
    output = {"experiment": "live endpoint evaluation", "dataset_tasks": len(rows),
              "evaluated_tasks": len(records), "successful_tasks": successes,
              "success_rate_evaluated": successes / len(records) if records else None,
              "completed_fraction": len(records) / len(rows), "spent": str(spent),
              "total_budget": str(cap), "budget_overrun": spent > cap,
              "usage_estimated": any(a["usage_estimated"] for r in records for a in r["attempts"]),
              "billing_uncertain": any(r["billing_uncertain"] for r in records),
              "policy": config["routing"]["type"],
              "models": config["models"], "records": records}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(args.out, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: value for key, value in output.items() if key not in ("records", "models")}))
    return 0 if records and len(records) == len(rows) and not output["billing_uncertain"] and not output["budget_overrun"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
