import json
from pathlib import Path


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root = Path("results/offline")
    report = json.loads((root / "summary.json").read_text())
    sensitivity = json.loads((root / "sensitivity.json").read_text())
    context = json.loads((root / "context_study.json").read_text())
    names = list(report["policies"])
    labels = ["Always small", "Always large", "Cheap-first cascade", "Calibrated routing"]
    colors = ["#a7adb5", "#6b7480", "#536e83", "#1c4b47"]
    rows = list(report["policies"].values())
    plt.rcParams.update({"svg.hashsalt": "orchestration-report", "font.family": "DejaVu Sans",
                         "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    values = [[r["success_rate"] * 100 for r in rows],
              [r["simulated_cost"] / report["policies"]["always_large"]["simulated_cost"] * 100 for r in rows],
              [r["simulated_p95_ms"] for r in rows]]
    titles = ["Exact-match success (%)", "Simulated cost (large = 100)", "Modeled p95 latency (ms)"]
    for ax, numbers, title in zip(axes, values, titles):
        ax.barh(labels, numbers, color=colors, height=0.57)
        ax.invert_yaxis()
        ax.set_title(title, loc="left", pad=12)
        ax.set_xlim(0, max(numbers) * 1.22)
        for index, number in enumerate(numbers):
            ax.text(number + max(numbers) * 0.025, index, f"{number:.1f}", va="center", fontsize=9)
        ax.grid(axis="x", color="#eeeeee", zorder=0)
        ax.set_axisbelow(True)
    fig.suptitle("Synthetic replay • 300 held-out tasks • no live LLM inference", fontsize=12, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.91])
    fig.savefig(root / "routing_tradeoffs.svg", metadata={"Date": None}, bbox_inches="tight")
    plt.close(fig)

    table = ["| Policy | Success | Simulated cost units | Cost / success | Calls | Modeled p95 |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, r in zip(labels, rows):
        table.append(f"| {name} | {r['successful_tasks']}/{r['tasks']} ({r['success_rate']:.2%}) | {r['simulated_cost']:.7f} | {r['simulated_cost_per_success']:.7f} | {r['calls']} | {r['simulated_p95_ms']:.0f} ms |")
    comparisons = report["comparison"]
    low, high = comparisons["paired_bootstrap_savings_95"]
    body = "\n".join([
        "# Recorded evaluation results", "",
        "**Evidence level: synthetic replay and local software tests. No live model calls were made.**", "",
        "The success rates below measure agreement with fixture answers. Costs use illustrative token rates; latency uses fixed provider delays. They are not measured API savings, paid invoices, or live-model speed measurements.", "",
        "![Routing tradeoffs](routing_tradeoffs.svg)", "", *table, "",
        "## Interpretation", "",
        f"- Calibrated routing uses {comparisons['simulated_savings_vs_large']:.2%} less simulated cost than always-large. The paired 2,000-resample bootstrap interval is {low:.2%}–{high:.2%}, conditional on this artificial dataset and cost model.",
        "- Cheap-first is cheaper than calibrated routing. Calibrated routing pays more to avoid many failed first attempts and reduce the modeled p95 from 710 ms to 450 ms.",
        "- Both cascaded policies reach 299/300 with a perfect exact-match verifier. This does not demonstrate equivalent performance with a real-world verifier.",
        "- Offline execution time in summary.json is measured Python replay time, not model inference latency.", "",
        "## Controlled changes", "",
        "| Scenario | Accepted | Ground-truth correct | False accepts | Calls | Simulated cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name, row in sensitivity["scenarios"].items():
        body += f"\n| {name} | {row['accepted']} | {row['correct']} | {row['false_accepts']} | {row['calls']} | {row['simulated_cost']:.7f} |"
    body += "\n\nThe imperfect-verifier control injects a 10% false-positive probability and a 5% false-negative probability using a deterministic hash of task ID and output. These rates are experimental assumptions, not measured verifier performance. Identical answers receive correlated verdicts. Budget cases use conservative preflight estimates; a task may be skipped even when its realized short response would have fit.\n"
    body += f"\n## Dependency handoff control\n\nTwo interleaved six-step chains execute 12 scripted agent tasks. Direct-dependency handoffs send {context['selective']['context_characters']:,} characters versus {context['full_history']['context_characters']:,} for full history: a {context['context_character_reduction']:.2%} reduction. Both workflows pass their scripted evidence checks. Estimated input tokens are {context['selective']['estimated_input_tokens']:,} versus {context['full_history']['estimated_input_tokens']:,}. This is structural context elimination, not semantic compression or demonstrated LLM quality retention.\n"
    body += "\n## Reproduction and evidence\n\n```bash\npython -m evaluation.run\npython -m evaluation.context_study\npython -m evaluation.sensitivity\npython -m evaluation.report\n```\n\nThe final plotting command requires matplotlib. The engine, tests, and numerical experiments use the Python standard library.\n\n"
    body += f"- Seed: `{report['seed']}`; calibration: {report['calibration_tasks']} tasks; held-out: {report['test_tasks']} tasks.\n- Python: `{report['python']}`.\n- Code digest: `{report['source_sha256']}`.\n- Calibration fixture digest: `{report['train_sha256']}`.\n- Test fixture digest: `{report['test_sha256']}`.\n"
    body += "\nFiles: [summary.json](summary.json), [summary.csv](summary.csv), [raw traces](traces.jsonl), [calibration](calibration.json), [test fixtures](test_fixtures.jsonl), [sensitivity](sensitivity.json), [sensitivity traces](sensitivity_traces.jsonl), [context control](context_study.json). Wall-clock measurements vary between runs; deterministic outcomes and simulated totals should reproduce.\n"
    (root / "RESULTS.md").write_text(body)


if __name__ == "__main__":
    main()
