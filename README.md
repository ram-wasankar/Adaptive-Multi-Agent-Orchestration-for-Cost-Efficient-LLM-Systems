# Adaptive Multi-Agent Orchestration for Cost-Efficient LLM Systems

Throwing the biggest model at every task gets expensive fast. I built this project to explore a more practical approach: choose a suitable model, check its answer, and escalate when another call is worth the cost.

The system coordinates agent workflows across model providers, passes relevant context between tasks, and tracks spending throughout execution. The idea is simple: make every extra call earn its keep.

[Full case study](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/CASE_STUDY.md) · [Results](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/results/offline/RESULTS.md) · [Setup](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/docs/USAGE.md)

## What it does

- Routes tasks using fixed-model, cheap-first, or calibrated routing policies.
- Coordinates agent roles through explicit task dependencies.
- Validates responses before accepting them and escalates rejected answers.
- Passes dependency evidence instead of replaying the entire workflow history.
- Tracks token costs, checks budgets, and handles retries and uncertain billing.
- Connects to compatible hosted APIs or self-hosted inference endpoints.

The Python engine, tests, and numerical experiments use the standard library. Matplotlib is needed only to regenerate the chart.

## Results so far

Across 300 held-out synthetic tasks, calibrated routing achieved **99.67% exact-match success** with **49.14% lower modeled inference cost** than the always-large baseline.

| Policy              | Exact-match success | Calls | Simulated cost units |
| ------------------- | ------------------: | ----: | -------------------: |
| Always small        |              52.33% |   300 |            0.0017965 |
| Always large        |              97.00% |   300 |            0.0269475 |
| Cheap-first cascade |              99.67% |   474 |            0.0083838 |
| Calibrated routing  |              99.67% |   322 |            0.0137054 |

Calibrated routing used **49.14% less simulated cost** than always-large. Cheap-first was cheaper still, but needed more calls and had higher modeled tail latency. No free lunch—the right policy depends on what you’re optimizing.

A separate 12-task handoff experiment reduced transmitted context characters by **84.86%** through direct-dependency selection. The repository also includes **36 passing software tests**.

[See the full results, assumptions, and ablations](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/results/offline/RESULTS.md).

## Run it locally

Requires Python 3.11+.

```bash
git clone https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems.git
cd Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems

python -m unittest discover -s tests -v
python -m evaluation.run
python -m evaluation.context_study
python -m evaluation.sensitivity
```

These experiments run offline without API credentials. For real endpoints, follow the [configuration and live evaluation instructions](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/docs/USAGE.md).

## Dig deeper

- [Case study](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/CASE_STUDY.md): the problem, design decisions, findings, and limitations.
- [Architecture](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/docs/ARCHITECTURE.md): execution flow, interfaces, and failure handling.
- [Evaluation protocol](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/docs/EVALUATION.md): fixture construction, baselines, and measurement boundaries.
- [Raw traces](https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems/blob/main/results/offline/traces.jsonl): inspect individual routing decisions and attempts.

## What’s next

Measure actual models on representative workloads, account for hosting and verification costs, and test how routing behaves when the workload changes. The implementation is here; real-world performance claims need real-world runs.
