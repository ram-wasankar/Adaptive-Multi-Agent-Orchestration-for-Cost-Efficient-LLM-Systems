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
    plt.rcParams.update({
        "svg.hashsalt": "orchestration-report", "font.family": "DejaVu Serif",
        "mathtext.fontset": "dejavuserif", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "axes.linewidth": 0.6,
        "xtick.major.width": 0.6, "xtick.major.size": 3,
        "ytick.major.size": 0, "text.color": "#222222",
        "axes.labelcolor": "#222222", "xtick.color": "#333333",
        "ytick.color": "#222222", "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white",
    })
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.8), sharey=True)
    positions = list(range(len(rows)))
    values = [[r["success_rate"] * 100 for r in rows],
              [r["simulated_cost"] * 1000 for r in rows],
              [r["simulated_p95_ms"] for r in rows]]
    titles = ["(a) Task success", "(b) Total simulated cost", "(c) Modeled tail latency"]
    xlabels = ["Exact-match success (%)", r"Cost units ($\times 10^{-3}$)", "p95 latency (ms)"]
    limits = [(0, 118), (0, 34), (0, 880)]
    ticks = [[0, 25, 50, 75, 100], [0, 10, 20, 30], [0, 200, 400, 600, 800]]
    for panel, (ax, numbers, title, xlabel) in enumerate(zip(axes, values, titles, xlabels)):
        ax.set_title(title, loc="left", pad=13, fontsize=10)
        ax.set_xlim(*limits[panel])
        ax.set_xticks(ticks[panel])
        ax.set_xlabel(xlabel, labelpad=8, fontsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e5e5e5", linewidth=0.5)
        if panel == 0:
            lower = [r["success_rate_wilson_95"][0] * 100 for r in rows]
            upper = [r["success_rate_wilson_95"][1] * 100 for r in rows]
            ax.errorbar(numbers, positions,
                        xerr=[[n-lo for n, lo in zip(numbers, lower)],
                              [hi-n for n, hi in zip(numbers, upper)]],
                        fmt="o", markersize=4.5, color="#222222", ecolor="#444444",
                        elinewidth=0.9, capsize=3, capthick=0.8, zorder=3)
            # Place annotations beyond the interval, not on the whiskers.
            for y, number, hi in zip(positions, numbers, upper):
                ax.annotate(f"{number:.1f}", (hi, y), xytext=(5, 0),
                            textcoords="offset points", va="center", fontsize=8)
        else:
            ax.hlines(positions, 0, numbers, color="#bbbbbb", linewidth=0.8)
            ax.plot(numbers, positions, "o", markersize=4.5, color="#222222", zorder=3)
            for y, number in zip(positions, numbers):
                label = f"{number:.2f}" if panel == 1 else f"{number:.0f}"
                ax.annotate(label, (number, y), xytext=(6, 0),
                            textcoords="offset points", va="center", fontsize=8)
    axes[0].set_yticks(positions, labels, fontsize=9)
    axes[0].set_ylim(3.5, -0.5)
    fig.subplots_adjust(left=0.20, right=0.985, top=0.84, bottom=0.29, wspace=0.28)
    fig.text(0.02, 0.10,
             f"Synthetic replay; {report['test_tasks']} held-out tasks. Whiskers: 95% Wilson intervals for task success.",
             fontsize=8, color="#444444")
    fig.text(0.02, 0.035, "Cost uses illustrative token rates; latency uses fixed provider delays.",
             fontsize=8, color="#444444")
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

