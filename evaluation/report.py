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
    names = ["always_small", "always_large", "cheap_first_cascade", "calibrated_routing"]
    labels = ["Always small", "Always large", "Cheap-first cascade", "Calibrated routing"]
    rows = [report["policies"][name] for name in names]
    colors = ["#9aa9b7", "#52677d", "#c28a42", "#087f8c"]
    plt.rcParams.update({
        "svg.hashsalt": "orchestration-report", "font.family": "DejaVu Sans",
        "font.size": 10, "text.color": "#172d46", "axes.labelcolor": "#41546a",
        "axes.edgecolor": "#b9c5cf", "axes.linewidth": 0.7,
        "xtick.color": "#526477", "ytick.color": "#526477",
        "xtick.major.size": 0, "ytick.major.size": 0,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.8),
                             gridspec_kw={"width_ratios": [1.65, 1]})
    quality, latency = axes
    costs = [r["simulated_cost"] / report["policies"]["always_large"]["simulated_cost"] * 100 for r in rows]
    success = [r["success_rate"] * 100 for r in rows]
    offsets = [(16, 12), (-8, -95), (-12, 22), (15, -32)]
    alignments = ["left", "right", "right", "left"]
    for i, (cost, rate, row, color) in enumerate(zip(costs, success, rows, colors)):
        lo, hi = [v * 100 for v in row["success_rate_wilson_95"]]
        quality.errorbar(cost, rate, yerr=[[rate-lo], [hi-rate]], color=color,
                         fmt="o", markersize=9, elinewidth=1.5, capsize=3.5,
                         markeredgecolor="white", markeredgewidth=1.2, zorder=4)
        quality.annotate(f"{labels[i]}\n{rate:.1f}% success · {cost:.1f}% cost",
                         (cost, rate), xytext=offsets[i], textcoords="offset points",
                         ha=alignments[i], va="bottom" if i in (0, 2) else "top",
                         fontsize=9, linespacing=1.6, color="#172d46",
                         arrowprops={"arrowstyle": "-", "color": color, "lw": 0.8,
                                     "shrinkA": 6, "shrinkB": 8})
    quality.set_xlim(0, 118)
    quality.set_ylim(40, 111)
    quality.set_xticks([0, 25, 50, 75, 100])
    quality.set_yticks([40, 60, 80, 100])
    quality.set_xlabel("Modeled cost (% of always-large)", labelpad=12, fontsize=10)
    quality.set_ylabel("Exact-match success (%)", labelpad=10, fontsize=10)
    quality.set_title("QUALITY / COST", loc="left", fontsize=10, fontweight="bold", pad=20)
    quality.grid(color="#e9eef2", linewidth=0.7)
    quality.set_axisbelow(True)
    bars = latency.bar(range(4), [r["simulated_p95_ms"] for r in rows],
                       color=colors, width=0.52, zorder=3)
    for bar, row in zip(bars, rows):
        latency.text(bar.get_x()+bar.get_width()/2, bar.get_height()+22,
                     f'{row["simulated_p95_ms"]:.0f}', ha="center", fontsize=11,
                     fontweight="medium", color="#172d46")
    latency.set_xticks(range(4), ["Always\nsmall", "Always\nlarge",
                                  "Cheap-first\ncascade", "Calibrated\nrouting"], fontsize=9)
    latency.set_ylim(0, 850)
    latency.set_yticks([0, 200, 400, 600, 800])
    latency.set_ylabel("Modeled p95 latency (ms)", labelpad=10, fontsize=10)
    latency.set_title("TAIL LATENCY", loc="left", fontsize=10, fontweight="bold", pad=20)
    latency.grid(axis="y", color="#e9eef2", linewidth=0.7)
    latency.set_axisbelow(True)
    latency.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.73, bottom=0.24, wspace=0.30)
    fig.text(0.035, 0.94, "Routing performance & resource trade-offs",
             fontsize=19, color="#172d46", fontweight="medium", va="top")
    fig.text(0.035, 0.865,
             f'{report["test_tasks"]} held-out tasks  /  Synthetic replay  /  Four routing policies',
             fontsize=10, color="#63758a")
    fig.text(0.035, 0.105,
             "Vertical whiskers show 95% Wilson intervals. Lower cost and higher success are preferable.",
             fontsize=8.5, color="#63758a")
    fig.text(0.035, 0.055,
             "Costs use illustrative token rates; latency uses fixed provider delays.",
             fontsize=8.5, color="#63758a")
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

