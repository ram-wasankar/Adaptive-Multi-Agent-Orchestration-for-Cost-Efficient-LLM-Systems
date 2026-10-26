import hashlib
import time
from dataclasses import asdict, dataclass
from decimal import Decimal

from .context import ContextOverflow, build_messages
from .routing import Router
from .types import Model, Provider, ProviderError, Task, estimate_tokens, money


@dataclass
class Attempt:
    task_id: str
    model: str
    provider: str
    status: str
    cost: str = "0"
    input_tokens: int = 0
    output_tokens: int = 0
    provider_latency_ms: float = 0
    wall_ms: float = 0
    context_chars: int = 0
    output_sha256: str = ""
    usage_estimated: bool = False
    detail: str = ""


@dataclass
class TaskResult:
    task_id: str
    status: str
    output: str | None = None
    model: str | None = None


@dataclass
class Run:
    tasks: list[TaskResult]
    attempts: list[Attempt]
    spent: Decimal
    budget: Decimal
    billing_uncertain: bool = False
    wall_ms: float = 0

    @property
    def success(self):
        return bool(self.tasks) and all(task.status == "success" for task in self.tasks)

    def to_dict(self, include_outputs: bool = False):
        tasks = [asdict(task) for task in self.tasks]
        if not include_outputs:
            for task in tasks:
                task.pop("output")
        return {"success": self.success, "tasks": tasks,
                "attempts": [asdict(a) for a in self.attempts],
                "spent": str(self.spent), "budget": str(self.budget),
                "billing_uncertain": self.billing_uncertain, "wall_ms": self.wall_ms}


def topological_order(tasks: list[Task]) -> list[Task]:
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("Task identifiers must be unique")
    if not tasks:
        raise ValueError("At least one task is required")
    for task in tasks:
        if any(dep not in by_id for dep in task.dependencies):
            raise ValueError(f"Unknown dependency for {task.id}")
    ordered, done = [], set()
    while len(done) < len(tasks):
        ready = [task for task in tasks if task.id not in done and
                 all(dep in done for dep in task.dependencies)]
        if not ready:
            raise ValueError("Dependency graph contains a cycle")
        ordered.extend(ready)
        done.update(task.id for task in ready)
    return ordered


class Orchestrator:
    """Sequential DAG executor. Each task is an agent role; no hidden planning calls."""

    def __init__(self, models: list[Model], providers: dict[str, Provider], router: Router,
                 budget: str = "1", context_chars: int = 12000, retries: int = 1,
                 retry_backoff: float = 0.1, full_history: bool = False):
        if not models or len({m.name for m in models}) != len(models):
            raise ValueError("Models must be non-empty and uniquely named")
        if any(m.provider not in providers for m in models):
            raise ValueError("A provider is missing")
        if context_chars < 0 or retries < 0 or retry_backoff < 0:
            raise ValueError("Limits cannot be negative")
        self.models, self.providers, self.router = models, providers, router
        self.budget = money(budget)
        self.context_chars = context_chars
        self.retries, self.retry_backoff = retries, retry_backoff
        self.full_history = full_history

    def run(self, tasks: list[Task]) -> Run:
        ordered = topological_order(tasks)
        run = Run([], [], Decimal(0), self.budget)
        artifacts, statuses = {}, {}
        start = time.monotonic()
        for task in ordered:
            if run.billing_uncertain or run.spent > run.budget:
                result = TaskResult(task.id, "budget_halted")
            elif any(statuses[dep] != "success" for dep in task.dependencies):
                result = TaskResult(task.id, "dependency_failed")
            else:
                try:
                    messages, chars = build_messages(task, artifacts, self.context_chars,
                                                     self.full_history)
                except ContextOverflow:
                    result = TaskResult(task.id, "context_limit")
                else:
                    result = self._execute(task, messages, chars, run)
            run.tasks.append(result)
            statuses[task.id] = result.status
            if result.status == "success":
                artifacts[task.id] = result.output
        run.wall_ms = (time.monotonic() - start) * 1000
        return run

    def _execute(self, task, messages, context_chars, run):
        estimate = estimate_tokens(messages)
        ordered = self.router.order(task, self.models, estimate)
        names = [m.name for m in ordered]
        if len(names) != len(set(names)) or any(m not in self.models for m in ordered):
            raise ValueError("Router returned duplicate or unknown models")
        last_status = "no_eligible_model"
        for model in ordered:
            if estimate + task.max_output_tokens > model.context_window:
                run.attempts.append(Attempt(task.id, model.name, model.provider, "context_window"))
                last_status = "context_window"
                continue
            reservation = model.cost(estimate, task.max_output_tokens)
            if run.spent + reservation > run.budget:
                run.attempts.append(Attempt(task.id, model.name, model.provider, "budget_skipped"))
                last_status = "budget_exhausted"
                continue
            for retry in range(self.retries + 1):
                begun = time.monotonic()
                attempt = Attempt(task.id, model.name, model.provider, "started",
                                  context_chars=context_chars)
                try:
                    response = self.providers[model.provider].complete(model, task, messages)
                except ProviderError as error:
                    attempt.wall_ms = (time.monotonic() - begun) * 1000
                    attempt.status = "provider_error"
                    attempt.detail = str(error)
                    if error.billing_unknown:
                        run.spent += reservation
                        attempt.cost = str(reservation)
                        run.billing_uncertain = True
                    run.attempts.append(attempt)
                    if error.billing_unknown:
                        return TaskResult(task.id, "billing_unknown")
                    if error.retryable and retry < self.retries:
                        time.sleep(self.retry_backoff * (2 ** retry))
                        continue
                    last_status = "provider_error"
                    break
                charged = model.cost(response.input_tokens, response.output_tokens)
                run.spent += charged
                attempt.cost = str(charged)
                attempt.input_tokens = response.input_tokens
                attempt.output_tokens = response.output_tokens
                attempt.provider_latency_ms = response.latency_ms
                attempt.usage_estimated = response.usage_estimated
                attempt.output_sha256 = hashlib.sha256(response.text.encode()).hexdigest()
                if run.spent > run.budget:
                    attempt.status = "budget_overrun"
                else:
                    try:
                        verdict = task.validate(response.text)
                        attempt.status = "accepted" if verdict.passed else "rejected"
                        attempt.detail = verdict.reason
                    except Exception:
                        attempt.status = "validator_error"
                        attempt.detail = "Validator raised an exception"
                attempt.wall_ms = (time.monotonic() - begun) * 1000
                run.attempts.append(attempt)
                if attempt.status == "budget_overrun":
                    return TaskResult(task.id, "budget_overrun")
                if attempt.status == "accepted":
                    return TaskResult(task.id, "success", response.text, model.name)
                if attempt.status == "validator_error":
                    return TaskResult(task.id, "validator_error")
                last_status = "validation_failed"
                break
        return TaskResult(task.id, last_status)
