# Architecture and extension points

[Case study](../CASE_STUDY.md) · [Usage](USAGE.md) · [Evaluation protocol](EVALUATION.md)

The core is a sequential dependency-graph executor. A task is a prompted agent role with an ID, task family, dependencies, output limit, and validator. Model choice and provider transport are separate interfaces. An agent can use a different model or provider from its predecessor.

## Source map

| Module | Responsibility |
| --- | --- |
| `orchestration/types.py` | Model pricing, tasks, provider results, errors, and token estimate |
| `orchestration/routing.py` | Fixed, cheap-first, and calibrated ranking policies |
| `orchestration/context.py` | Direct-dependency artifact selection and provenance |
| `orchestration/engine.py` | Graph ordering, admission, execution, validation, escalation, ledger |
| `orchestration/providers.py` | OpenAI-compatible HTTP transport |
| `orchestration/validation.py` | Exact-match and JSON-shape validators |
| `orchestration/cli.py` | JSON configuration and workflow execution |
| `evaluation/` | Deterministic experiments, reporting, and opt-in live evaluation |

## Minimal Python integration

```python
from orchestration import Model, Orchestrator, Task
from orchestration.providers import OpenAICompatibleProvider
from orchestration.routing import CascadeRouter
from orchestration.validation import exact_match

engine = Orchestrator(
    models=[Model("local", "server", "your-served-model", "0.10", "0.20")],
    providers={"server": OpenAICompatibleProvider("http://127.0.0.1:8000/v1")},
    router=CascadeRouter(),
    budget="0.01",
)
task = Task("addition", "Return only the integer: 17 + 25", "arithmetic",
            exact_match("42"), max_output_tokens=16)
# This is a live endpoint call. Configure the server and real cost rates first.
run = engine.run([task])
print(run.to_dict())
```

`Model` rates use `Decimal` arithmetic. All rates and budgets must share a unit. The engine does not convert currencies or discover provider prices. A self-hosted token-rate allocation is a modeling choice, not a measurement of electricity or GPU utilization.

## Execution contract

The entire graph is validated before requests begin. Stable topological ordering follows input order within each ready group. Execution is sequential, including independent tasks. Each run starts a fresh ledger and artifact map. Do not mutate an engine's configuration concurrently with a run; there is no concurrency or distributed coordination contract.

A router returns an ordered subset of configured models without duplicates. The executor checks combined estimated context and output allowance, then estimated affordability, before each call. Ranking and admission are separate: the first ranked model can be skipped. Responses that fail validation still consume reported cost. The first accepted answer becomes the task artifact.

After a parent fails, descendants are blocked. Independent tasks continue unless uncertain billing or an observed budget overrun has stopped the workflow. Evidence above the configured character cap fails explicitly. No silent artifact truncation occurs.

| Task status | Meaning |
| --- | --- |
| `success` | A response passed the supplied validator |
| `validation_failed` | Last attempted model returned an unacceptable response |
| `dependency_failed` | At least one required parent did not succeed |
| `context_limit` | Serialized dependency evidence exceeded the character cap |
| `context_window` | Last candidate could not fit estimated input plus output allowance |
| `budget_exhausted` | Last candidate was skipped because its reservation did not fit |
| `budget_overrun` | Actual returned usage exceeded the remaining ledger budget |
| `billing_unknown` | A request may have been billed but its usage is unknown |
| `budget_halted` | An earlier overrun or uncertain bill prevented execution |
| `provider_error` | Last attempted provider failed without uncertain billing |
| `validator_error` | The validator raised an exception |
| `no_eligible_model` | The router returned no candidates |

The terminal status reflects the last relevant event, not an aggregate explanation of all rejected candidates. Use the attempt trace for the full sequence. Admission-only entries such as `budget_skipped` do not represent HTTP calls. A paid accepted/rejected entry contains usage and cost; uncertain billing records a provisional reservation.

## Provider contract

Implement `complete(model, task, messages) -> Completion`. Return nonnegative integer token usage and indicate estimates with `usage_estimated=True`. Report latency in milliseconds. Raise `ProviderError` for expected transport failures; set billing certainty conservatively. Unexpected implementation errors propagate instead of being silently retried.

The supplied adapter sends only the model identifier, messages, output limit, temperature, and streaming setting. It does not send the task's verifier or gold answer. It validates basic response shape and usage fields, refuses redirects, limits response bytes, and avoids putting raw response bodies in errors. It has no automatic retries; the engine owns retry decisions.

HTTP 429 is treated as an explicit non-billed retryable rejection. Selected client errors are non-billed and non-retryable. Timeout, malformed successful responses, and ambiguous server failures halt execution with uncertain billing. These classifications are integration assumptions; adapt them for a provider whose billing behavior differs.

## Validation and data handling

A validator returns `Verdict(passed, reason)`. Exact matching is appropriate for deterministic answers; JSON shape alone is not evidence of truth. The engine does not itself charge for an external judge called inside a custom validator. If verification incurs inference costs, include them in a separate ledger or extend the execution model before comparing total costs.

Handoffs contain producer IDs, output text, and SHA-256 digests. Digests provide content identity, not authentication or access control. The default trace excludes output text but includes IDs, usage, hashes, and validator reasons. Custom providers and validators are responsible for safe error strings. A live trace can still contain sensitive metadata.

## Deliberate boundaries

The implementation provides explicit roles, dependency handoffs, cross-provider routing, and verified escalation. It does not include an autonomous planner, tool sandbox, parallel execution, persistent state, model hosting, semantic retrieval, streaming, prompt caching, or production telemetry. Those can be evaluated as separate additions without obscuring the current cost and quality comparisons.
