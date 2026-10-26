from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Protocol


def money(value: str | int | float | Decimal) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("Money values must be finite and non-negative")
    return number


@dataclass(frozen=True)
class Model:
    name: str
    provider: str
    remote_model: str
    input_per_million: Decimal
    output_per_million: Decimal
    context_window: int = 8192

    def __post_init__(self):
        object.__setattr__(self, "input_per_million", money(self.input_per_million))
        object.__setattr__(self, "output_per_million", money(self.output_per_million))
        if not self.name or not self.provider or not self.remote_model or self.context_window < 1:
            raise ValueError("Model identifiers and a positive context window are required")

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Negative token count")
        return (self.input_per_million * input_tokens +
                self.output_per_million * output_tokens) / Decimal(1_000_000)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    kind: str
    validate: Callable[[str], Verdict] = field(repr=False, compare=False)
    dependencies: tuple[str, ...] = ()
    max_output_tokens: int = 256
    role: str = "Complete the task using the supplied evidence."

    def __post_init__(self):
        if not self.id or not self.prompt or self.max_output_tokens < 1:
            raise ValueError("Task id, prompt and positive output limit are required")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Repeated dependency")


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    usage_estimated: bool = False


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False,
                 billing_unknown: bool = True):
        super().__init__(message)
        self.retryable = retryable
        self.billing_unknown = billing_unknown


class Provider(Protocol):
    def complete(self, model: Model, task: Task,
                 messages: list[dict[str, str]]) -> Completion: ...


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """Conservative byte-based estimate; not a model tokenizer or billing guarantee."""
    return 32 + sum(len(m["content"].encode("utf-8")) + 8 for m in messages)
