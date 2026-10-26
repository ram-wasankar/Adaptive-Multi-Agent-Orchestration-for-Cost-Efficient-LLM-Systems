# Run the project

[Case study](../CASE_STUDY.md) · [Results](../results/offline/RESULTS.md) · [Architecture](ARCHITECTURE.md)

Python 3.11 or newer is required. The engine, numerical experiments, and tests have no third-party runtime dependencies. Run commands from the repository root.

## Offline reproduction

```bash
git clone https://github.com/ram-wasankar/Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems.git
cd Adaptive-Multi-Agent-Orchestration-for-Cost-Efficient-LLM-Systems
python -m unittest discover -s tests -v
python -m evaluation.run
python -m evaluation.context_study
python -m evaluation.sensitivity
```

These commands perform no external model calls. The HTTP adapter tests start a temporary loopback server. Results are written under `results/offline/`; replay wall times vary, while fixture answers, costs, and policy decisions are deterministic for the recorded seed. The checked-in [results report](../results/offline/RESULTS.md) includes all three experiments.

To regenerate the chart and Markdown report:

```bash
python -m pip install matplotlib==3.10.8
python -m evaluation.report
```

For installation into a virtual environment, `python -m pip install -e .` also exposes the `orchestrate` command. Installation is optional when running modules from the repository root. The `evaluation` package is a source-checkout tool, not part of the installed engine package.

## Configure real inference

Copy `examples/config.example.json` to `config.local.json`, which is ignored by Git. Replace each endpoint and served model name. The example points at two local OpenAI-compatible servers; it does not start servers, download weights, or provision GPUs. A compatible self-hosted vLLM server is one integration option. Hosted compatible endpoints can be used through the same adapter.

Set these values explicitly:

| Field | Meaning |
| --- | --- |
| `providers.<name>.base_url` | Base URL ending at the API root, typically `/v1`; the adapter appends `/chat/completions` |
| `providers.<name>.api_key_env` | Optional environment variable name containing the key; never the key itself |
| `providers.<name>.timeout` | Request timeout in seconds; default 45 |
| `models[].remote_model` | Exact model identifier served by that endpoint |
| `models[].input_per_million`, `output_per_million` | Cost rates in a consistent unit; example values are placeholders |
| `models[].context_window` | Actual supported combined input/output token limit |
| `limits.budget` | Total workflow budget, or per-task budget when using the live evaluator |
| `limits.context_chars` | Maximum serialized dependency-artifact characters, excluding the task prompt |
| `limits.retries` | Additional retries after explicit rate-limit rejection; default 1 |

HTTPS is required except for loopback addresses. For authenticated endpoints, set the configured key environment variable in your execution environment. The adapter sends ordinary non-streaming Chat Completions requests with `temperature=0` and `max_tokens`; an endpoint requiring different fields needs a separate adapter.

```bash
python -m orchestration.cli --config config.local.json --workflow examples/workflow.json --allow-network
```

This command makes actual requests and can incur charges. Its output trace defaults to `results/live/run.json` with owner-only file permissions. Prompts and answer text are excluded by default; `--include-outputs` includes accepted answers. A missing network opt-in causes the CLI to exit before inference. A successful workflow returns exit code 0; a failed workflow returns 1; invalid CLI configuration returns 2.

The example workflow has an extraction agent and a dependent summary agent. Its extraction validator requires an exact string. The summary validator checks JSON shape only: it demonstrates integration, not semantic correctness. Replace validators with checks suitable for your task.

## Choose a policy

`{"type": "fixed", "model": "large"}` provides a single-model baseline. `{"type": "cascade"}` orders models by estimated request cost. A calibrated policy uses held-out development observations:

```json
{
  "type": "calibrated",
  "fallback": "large",
  "quality_target": 0.85,
  "observations": {
    "extraction": {"small": [90, 100], "large": [98, 100]},
    "reasoning": {"small": [40, 100], "large": [94, 100]}
  }
}
```

Each pair is `[successful_calibration_tasks, total_calibration_tasks]`. These example counts are illustrative. Collect observations from your actual models before using this policy to make performance claims. Do not copy synthetic observations into a real deployment and treat them as measured reliability.

## Evaluate a real endpoint

The live evaluator accepts JSON Lines with `id`, `prompt`, `kind`, `expected`, and optional `max_output_tokens`. It runs one configured policy with exact-match grading. Gold answers are used by the validator, not sent to the model.

```bash
python -m evaluation.live --config config.local.json --dataset examples/smoke_dataset.jsonl --total-budget 0.10 --allow-network
```

The three-item smoke dataset tests connectivity and output formatting. It is not a sufficient research benchmark. The evaluator applies both a per-task limit and a run-level cap; uncertain billing or observed overrun stops further requests. Estimates and provider behavior mean the cap is not a guaranteed invoice ceiling.

Run each baseline with its own configuration and a separate `--out` path. Keep the same held-out task set, models, rates, sampling settings, and grading rules. Log model versions, hardware, timestamps, and verifier costs separately. The evaluator's exit code indicates whether evaluation completed without billing uncertainty or overrun; inspect success metrics to assess answer quality.

Live traces and local configuration are excluded from version control by default. Review custom provider errors and validator reasons before sharing traces: custom integrations can put sensitive text into those fields.
