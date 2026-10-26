import argparse
import json
import os
from pathlib import Path

from .engine import Orchestrator
from .providers import OpenAICompatibleProvider
from .routing import CalibratedRouter, CascadeRouter, FixedRouter
from .types import Model, Task
from .validation import exact_match, json_keys


def load_tasks(data):
    tasks = []
    for item in data:
        validation = item["validation"]
        if validation["type"] == "exact":
            check = exact_match(validation["expected"])
        elif validation["type"] == "json_keys":
            check = json_keys(validation["required"])
        else:
            raise ValueError("Unsupported validation type")
        tasks.append(Task(item["id"], item["prompt"], item["kind"], check,
                          tuple(item.get("dependencies", [])),
                          item.get("max_output_tokens", 256),
                          item.get("role", "Complete the task using the supplied evidence.")))
    return tasks


def build_engine(config):
    models = [Model(**item) for item in config["models"]]
    providers = {name: OpenAICompatibleProvider(**item)
                 for name, item in config["providers"].items()}
    policy = config["routing"]
    if policy["type"] == "calibrated":
        router = CalibratedRouter(policy["observations"], policy["fallback"],
                                  policy.get("quality_target", 0.85))
    elif policy["type"] == "cascade":
        router = CascadeRouter()
    elif policy["type"] == "fixed":
        router = FixedRouter(policy["model"])
    else:
        raise ValueError("Unsupported routing policy")
    return Orchestrator(models, providers, router, **config["limits"])


def main():
    parser = argparse.ArgumentParser(description="Execute a configured model workflow")
    parser.add_argument("--config", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--output", default="results/live/run.json")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--include-outputs", action="store_true")
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("Live inference requires --allow-network and may incur provider charges")
    try:
        config = json.loads(Path(args.config).read_text())
        tasks = load_tasks(json.loads(Path(args.workflow).read_text())["tasks"])
        engine = build_engine(config)
        run = engine.run(tasks)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Restrictive permissions for potentially sensitive live traces.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.chmod(output, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(run.to_dict(args.include_outputs), handle, indent=2)
            handle.write("\n")
        print(json.dumps({"success": run.success, "spent": str(run.spent),
                          "billing_uncertain": run.billing_uncertain,
                          "trace": str(output)}))
        return 0 if run.success else 1
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
