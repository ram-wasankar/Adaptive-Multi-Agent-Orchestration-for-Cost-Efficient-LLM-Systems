import json
from pathlib import Path

from orchestration.engine import Orchestrator
from orchestration.routing import FixedRouter
from orchestration.types import Completion, Model, Task
from orchestration.validation import exact_match


class HandoffProvider:
    def __init__(self, outputs):
        self.outputs = outputs

    def complete(self, model, task, messages):
        user = messages[1]["content"]
        if task.dependencies:
            marker = "Dependency evidence (JSON):\n"
            evidence = {item["task_id"]: item["output"] for item in json.loads(user.split(marker)[1])}
            if any(evidence.get(dep) != self.outputs[dep] for dep in task.dependencies):
                return Completion("missing evidence", 1, 1, 0)
        output = self.outputs[task.id]
        input_tokens = 16 + sum((len(m["content"].encode()) + 3) // 4 for m in messages)
        return Completion(output, input_tokens, (len(output) + 3) // 4, 0)


def main():
    outputs = {f"agent-{i}": f"Artifact {i}: " + (f"evidence-{i} " * 100) for i in range(12)}
    tasks = []
    for i in range(12):
        # Two interleaved dependency chains: unrelated chain evidence is unnecessary.
        deps = (f"agent-{i-2}",) if i >= 2 else ()
        tasks.append(Task(f"agent-{i}", "Use the required evidence to complete this step.",
                          "handoff", exact_match(outputs[f"agent-{i}"]), deps, 512))
    provider = HandoffProvider(outputs)
    model = Model("fixture", "replay", "fixture", "1", "2", context_window=100000)
    report = {"experiment": "synthetic dependency handoff; outputs are scripted",
              "agents": 12, "topology": "two interleaved chains; direct dependencies required"}
    for name, full in (("selective", False), ("full_history", True)):
        run = Orchestrator([model], {"replay": provider}, FixedRouter("fixture"),
                           context_chars=100000, full_history=full).run(tasks)
        report[name] = {"success": run.success,
                        "context_characters": sum(a.context_chars for a in run.attempts),
                        "estimated_input_tokens": sum(a.input_tokens for a in run.attempts),
                        "trace": run.to_dict()}
    report["context_character_reduction"] = 1 - report["selective"]["context_characters"] / report["full_history"]["context_characters"]
    path = Path("results/offline/context_study.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("selective", "full_history")}, indent=2))


if __name__ == "__main__":
    main()
