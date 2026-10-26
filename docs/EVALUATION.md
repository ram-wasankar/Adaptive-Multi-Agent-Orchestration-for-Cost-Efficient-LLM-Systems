# Evaluation protocol and evidence boundaries

[Recorded results](../results/offline/RESULTS.md) · [Case study](../CASE_STUDY.md) · [Run instructions](USAGE.md)

## What was evaluated

The checked-in study evaluates routing and execution logic with deterministic synthetic responses. It does not execute a language model. A separate context experiment evaluates artifact selection over scripted agent dependencies. Software tests evaluate failure handling and HTTP integration against a local stub server. No real-model result is included.

## Fixture construction

The default seed is `20261026`. Calibration uses 80 tasks per family, 240 total. Test generation uses seed plus one and 100 tasks per family, 300 total. IDs include the split; calibration and test identifiers are disjoint. Families are extraction, arithmetic, and reasoning. The reasoning label represents a scripted task category, not demonstrated language-model reasoning ability.

For each task/model pair, a seeded hash determines whether the scripted answer equals the programmatically generated gold answer or a deliberately wrong answer. The following values are assumptions supplied to the generator:

| Model label | Extraction success probability | Arithmetic | Reasoning | Input / million | Output / million | Modeled latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 0.96 | 0.58 | 0.24 | 0.10 | 0.20 | 80 ms |
| medium | 0.98 | 0.93 | 0.68 | 0.40 | 0.80 | 180 ms |
| large | 0.99 | 0.98 | 0.96 | 1.50 | 3.00 | 450 ms |

Rates are arbitrary cost units, not quoted vendor pricing. Names are size labels, not actual model identities. Simulated usage uses a character-based estimate; budget preflight uses the core's more conservative byte estimate. The difference intentionally exposes admission behavior, but is not a calibrated tokenizer study.

The generator builds model-specific outcomes using hash inputs. It does not model realistic cross-model error correlations, changing server load, reasoning-token costs, caching, long outputs, or distribution shift. Synthetic response diversity and the ideal verifier make cascades particularly favorable. Conclusions remain conditional on these choices.

## Main comparison

All four policies receive identical test tasks and the same saved response for each task/model pair. Always-small and always-large make one attempt per task. The cheap-first cascade ranks by estimated cost. The calibrated policy fits a success table on calibration only, freezes it, and uses a 0.85 first-choice threshold with large-model fallback. Each task has a 0.05-unit budget.

Expected answers are used in exact-match validation and do not enter provider messages. The verifier is ideal and has zero modeled external cost. Model latency is summed across sequential attempts; routing and validation overhead are not added to modeled inference latency. Actual Python replay wall time is stored separately.

Metrics include exact-match successes, cumulative cost including rejected outputs, cost per successful task, call count, escalated tasks, usage, and nearest-rank p50/p95. Success intervals use the Wilson method. A paired bootstrap resamples the same 300 task indices for always-large and calibrated cost totals 2,000 times, then computes percentile bounds on relative savings. It conditions on the frozen routing table and does not account for uncertainty in the supplied probabilities, rates, model identities, or calibration process.

Calibration computation and model calls used to obtain calibration labels are excluded from inference cost totals. A live deployment must report and amortize those costs separately. Here calibration is generated offline and makes no paid calls.

## Controlled experiments

| Control | Question |
| --- | --- |
| Disable escalation | How much of the observed success comes from retries on other models? |
| Increase threshold to 0.95 | What extra spend follows a more conservative initial choice? |
| Imperfect verifier | How far can accepted answers diverge from correctness? |
| Tight budgets | Which requests are denied under conservative preflight admission? |
| Full history versus direct dependencies | How much irrelevant context can graph structure remove? |

The imperfect verifier injects a 10% false-positive probability and a 5% false-negative probability using a deterministic task-ID/output hash. Repeated identical answers receive the same verdict, so verdicts are correlated. Ground truth is checked separately after execution. These are assumed error rates, not a trained or measured verifier.

The context control uses two interleaved six-step chains and approximately 1,100-character scripted artifacts. Its stub provider checks that required parent evidence appears. The measured character reduction depends on graph topology and payload length; it is not an expected reduction for every workflow. Both policies have ample context windows in this control.

## Audit trail

`summary.json` records assumptions, per-family metrics, Python version, calibration/test SHA-256 digests, and a source digest. The source digest concatenates sorted path names and contents from `orchestration/*.py` and `evaluation/*.py`; it excludes tests and documentation. Fixture digests are based on canonical JSON representations. The fixture files preserve every scripted model response.

`traces.jsonl` contains the four policy runs for each test task. `sensitivity_traces.jsonl` preserves each controlled scenario. `context_study.json` includes both workflow traces. `results/verification.json` records the local test-run outcome. Wall times vary across machines and do not participate in fixture digests.

Reproduction is expected to recover deterministic answer counts, routing decisions, call counts, and simulated totals. Floating-point summary representation and chart layout may vary slightly across software versions. Ledger arithmetic itself uses decimal costs.

## Protocol for a publishable live-model claim

1. Specify actual model versions, serving stack, hardware, context limits, prices or GPU accounting, sampling settings, and experiment dates.
2. Choose representative held-out tasks with adequate sample size. Keep calibration separate, investigate benchmark contamination, and freeze routing before testing.
3. Use the same task set and comparable execution conditions for fixed-model, cascade, and calibrated policies. Randomize run ordering to reduce load/time effects.
4. Grade with task-appropriate checks. For subjective tasks, use independent review, measure judge agreement, and record verifier cost and errors.
5. Measure end-to-end latency, failures, queueing, actual token usage, GPU utilization where relevant, and all retry/calibration overhead. Report missing or uncertain charges.
6. Repeat under multiple seeds and workload distributions. Include confidence intervals, failure examples, budget sensitivity, and correlated model-error analysis.
7. Publish sanitized task data, configurations, traces, and exact reproduction steps when data permissions allow.

The opt-in live evaluator supplies basic exact-match execution and a run-level spending limit. It does not implement this complete experimental protocol. Its three-item smoke dataset is a connectivity check only.
