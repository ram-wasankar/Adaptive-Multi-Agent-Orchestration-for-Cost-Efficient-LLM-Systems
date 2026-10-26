import hashlib
import json
import random
from decimal import Decimal

from orchestration.types import Completion, Model, Task
from orchestration.validation import exact_match


FAMILIES = ("extraction", "arithmetic", "reasoning")
PROBABILITIES = {
    "small": (0.96, 0.58, 0.24),
    "medium": (0.98, 0.93, 0.68),
    "large": (0.99, 0.98, 0.96),
}
LATENCY_MS = {"small": 80, "medium": 180, "large": 450}


def models():
    return [Model("small", "replay_a", "synthetic-small", Decimal("0.10"), Decimal("0.20")),
            Model("medium", "replay_a", "synthetic-medium", Decimal("0.40"), Decimal("0.80")),
            Model("large", "replay_b", "synthetic-large", Decimal("1.50"), Decimal("3.00"))]


def make_dataset(split: str, per_family: int, seed: int):
    """Generate labeled fixtures and scripted outputs, not language-model samples."""
    rng = random.Random(seed)
    rows = []
    for family_index, family in enumerate(FAMILIES):
        for index in range(per_family):
            task_id = f"{split}-{family}-{index:04d}"
            a, b, c = rng.randrange(10, 500), rng.randrange(10, 500), rng.randrange(2, 8)
            if family == "extraction":
                prompt, expected = f"Return only the order ID from 'Order {a}; quantity {b}'.", str(a)
            elif family == "arithmetic":
                prompt, expected = f"Compute {a} + {b}. Return only the integer.", str(a + b)
            else:
                prompt = f"Each of {c} boxes has {a} items; {b} items are removed. How many remain? Return an integer."
                expected = str(c * a - b)
            responses = {}
            for model, probabilities in PROBABILITIES.items():
                digest = hashlib.sha256(f"{seed}:{task_id}:{model}".encode()).digest()
                uniform = int.from_bytes(digest[:8], "big") / 2**64
                passed = uniform < probabilities[family_index]
                responses[model] = expected if passed else str(int(expected) + 1)
            rows.append({"id": task_id, "kind": family, "prompt": prompt,
                         "expected": expected, "responses": responses})
    rng.shuffle(rows)
    return rows


def as_task(row):
    return Task(row["id"], row["prompt"], row["kind"], exact_match(row["expected"]),
                max_output_tokens=32)


class ReplayProvider:
    def __init__(self, rows):
        self.rows = {row["id"]: row for row in rows}

    def complete(self, model, task, messages):
        text = self.rows[task.id]["responses"][model.name]
        tokens = 16 + sum((len(m["content"].encode()) + 3) // 4 for m in messages)
        return Completion(text, tokens, max(1, (len(text) + 3) // 4), LATENCY_MS[model.name])


def calibration(rows):
    observations = {}
    for row in rows:
        family = observations.setdefault(row["kind"], {})
        for model, answer in row["responses"].items():
            wins, count = family.get(model, (0, 0))
            family[model] = (wins + int(answer == row["expected"]), count + 1)
    return observations


def digest_rows(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
