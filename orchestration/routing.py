from dataclasses import dataclass
from typing import Protocol

from .types import Model, Task


class Router(Protocol):
    def order(self, task: Task, models: list[Model], input_tokens: int) -> list[Model]: ...


@dataclass
class FixedRouter:
    model_name: str

    def order(self, task: Task, models: list[Model], input_tokens: int) -> list[Model]:
        selected = [m for m in models if m.name == self.model_name]
        if not selected:
            raise ValueError(f"Unknown fixed model: {self.model_name}")
        return selected


class CascadeRouter:
    def order(self, task: Task, models: list[Model], input_tokens: int) -> list[Model]:
        return sorted(models, key=lambda m: (m.cost(input_tokens, task.max_output_tokens), m.name))


class CalibratedRouter:
    """Task-family success estimates with additive smoothing, learned off-line.

    This is a transparent contextual lookup policy, not a neural router or bandit.
    The reliability target is a selection threshold, not a guarantee.
    """

    def __init__(self, observations: dict[str, dict[str, tuple[int, int]]],
                 fallback: str, quality_target: float = 0.85):
        if not 0 < quality_target <= 1:
            raise ValueError("Quality target must be in (0, 1]")
        for family in observations.values():
            for wins, count in family.values():
                if not 0 <= wins <= count:
                    raise ValueError("Invalid calibration counts")
        self.observations = observations
        self.fallback = fallback
        self.quality_target = quality_target

    def probability(self, kind: str, model: str) -> float:
        wins, count = self.observations.get(kind, {}).get(model, (0, 0))
        return (wins + 1) / (count + 2)

    def order(self, task: Task, models: list[Model], input_tokens: int) -> list[Model]:
        lookup = {m.name: m for m in models}
        if self.fallback not in lookup:
            raise ValueError("Fallback model is not configured")
        if task.kind not in self.observations:
            return [lookup[self.fallback]]
        eligible = [m for m in models
                    if self.probability(task.kind, m.name) >= self.quality_target]
        first = (min(eligible, key=lambda m: (m.cost(input_tokens, task.max_output_tokens), m.name))
                 if eligible else lookup[self.fallback])
        rest = sorted((m for m in models if m.name != first.name),
                      key=lambda m: (-self.probability(task.kind, m.name),
                                     m.cost(input_tokens, task.max_output_tokens), m.name))
        return [first, *rest]
