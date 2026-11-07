"""Plot saved quantum and classical results without rerunning the simulator.

Run: python src/plot_quantum_results.py
Add --show to also open the Matplotlib window.
"""

import argparse
import csv
import json
import os
from pathlib import Path

# Keep Matplotlib's font cache in a writable, ignored project directory.
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import matplotlib
import numpy as np


RESULTS = ROOT / "results"
TEAL = "#008579"
NAVY = "#25374A"
AMBER = "#C88D29"
LIGHT = "#E8EDF2"


def load_results(quantum_path, classical_path):
    with quantum_path.open(newline="", encoding="utf-8-sig") as source:
        quantum = sorted(csv.DictReader(source), key=lambda row: int(row["year"]))
    with classical_path.open(newline="", encoding="utf-8-sig") as source:
        classical = list(csv.DictReader(source))
    if not quantum or not classical:
        raise ValueError("Both results files must contain data.")

    industries = [key.removeprefix("quantum_") for key in quantum[0]
                  if key.startswith("quantum_")]
    if set(industries) != {row["industry"] for row in classical}:
        raise ValueError("Choose quantum and classical results for the same industry network.")
    reference = {(int(row["year"]), row["industry"]): row for row in classical}
    if len(reference) != len(classical):
        raise ValueError("The classical CSV contains duplicate industry/year records.")

    years, quantum_counts, classical_counts, hits, shots = [], [], [], [], []
    quantum_flips, classical_flips = {}, {}
    matching_energy_years = 0
    for row in quantum:
        year = int(row["year"])
        if year in years:
            raise ValueError("The quantum CSV contains duplicate years.")
        if any((year, name) not in reference for name in industries):
            raise ValueError(f"The classical results are missing industries for {year}.")
        years.append(year)
        q_count, c_count = 0, 0
        for name in industries:
            q_digital = int(row["quantum_" + name]) == 1
            c_digital = reference[(year, name)]["state"] == "Digital"
            q_count += q_digital
            c_count += c_digital
            if q_digital:
                quantum_flips.setdefault(name, year)
            if c_digital:
                classical_flips.setdefault(name, year)
        quantum_counts.append(q_count)
        classical_counts.append(c_count)
        year_shots, year_hits = int(row["shots"]), int(row["exact_hits"])
        if not 0 <= year_hits <= year_shots or year_shots <= 0:
            raise ValueError(f"Invalid measurement counts for {year}.")
        shots.append(year_shots)
        hits.append(year_hits)
        exact = float(reference[(year, industries[0])]["lowest_energy"])
        if not np.isclose(float(row["exact_energy"]), exact, rtol=0, atol=1e-8):
            raise ValueError("The two results files use different energy models.")
        matching_energy_years += np.isclose(float(row["best_energy"]), exact,
                                            rtol=0, atol=1e-8)

    metadata_path = quantum_path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    return {"years": np.array(years), "industries": industries,
            "quantum_counts": np.array(quantum_counts),
            "classical_counts": np.array(classical_counts),
            "hits": np.array(hits), "shots": np.array(shots),
            "quantum_flips": quantum_flips, "classical_flips": classical_flips,
            "matching_energy_years": int(matching_energy_years), "metadata": metadata}


def build_figure(data, source_name):
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 13, "axes.titleweight": "bold",
                         "axes.labelcolor": NAVY, "text.color": NAVY,
                         "xtick.color": NAVY, "ytick.color": NAVY,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#C8D1DB", "svg.fonttype": "none"})
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    grid = fig.add_gridspec(2, 2, left=0.065, right=0.965, bottom=0.15, top=0.79,
                           width_ratios=[1.22, 1], wspace=0.46, hspace=0.60)
    adoption = fig.add_subplot(grid[0, 0])
    measurements = fig.add_subplot(grid[1, 0])
    flips = fig.add_subplot(grid[:, 1])

    years = data["years"]
    count = len(data["industries"])
    metadata = data["metadata"]
    is_simulation = metadata.get("backend") == "aer_simulator" or "aer_simulator" in source_name
    backend_label = "Qiskit Aer simulation" if is_simulation else metadata.get("backend", "Quantum samples")
    settings = [f"{count} industries", f"{len(years)} years", backend_label]
    if metadata:
        settings += [f"{metadata['layers']} ramp layers", f"{metadata['shots_per_year']:,} measurements/year"]
    fig.text(0.065, 0.935, "Quantum and classical tipping points", fontsize=25, weight="bold")
    fig.text(0.065, 0.89, "  |  ".join(settings), fontsize=11, color="#617184")
    matching_flips = sum(data["quantum_flips"].get(name) == data["classical_flips"].get(name)
                         for name in data["industries"])
    fig.text(0.065, 0.842,
             f"{data['matching_energy_years']}/{len(years)} energy minima matched"
             f"     |     {matching_flips}/{count} industry flip years matched",
             fontsize=12, color=TEAL, weight="bold")

    # Different line styles make the equal classical and quantum values visible.
    adoption.step(years, data["classical_counts"], where="post", color=NAVY,
                  linewidth=3.7, linestyle="--", label="Classical exact", zorder=2)
    adoption.step(years, data["quantum_counts"], where="post", color=TEAL,
                  linewidth=2, label="Quantum best sample", zorder=3)
    adoption.scatter(years, data["quantum_counts"], s=17, color=TEAL, zorder=4)
    adoption.set(title="Industries becoming digital", ylabel="Industries digital",
                 xlim=(years[0] - 0.35, years[-1] + 0.35), ylim=(-0.6, count + 2))
    adoption.set_xticks(years[::2])
    adoption.set_yticks(range(0, count + 1, max(1, count // 4)))
    adoption.grid(axis="y", color=LIGHT)
    adoption.legend(loc="upper left", frameon=False, fontsize=9)
    changes = np.diff(data["quantum_counts"], prepend=data["quantum_counts"][0])
    biggest = int(changes.argmax())
    if changes[biggest] > 0:
        adoption.annotate(f"{changes[biggest]} industries switch\nin {years[biggest]}",
                          xy=(years[biggest], data["quantum_counts"][biggest]),
                          xytext=(0.42, 0.62), textcoords="axes fraction", fontsize=10,
                          arrowprops={"arrowstyle": "->", "color": AMBER, "lw": 1.6},
                          bbox={"facecolor": "white", "edgecolor": "none", "pad": 4})

    # Measurement counts are distinct from the number of digital industries.
    measurements.bar(years, data["hits"], width=0.73, color=TEAL, label="Minimum energy")
    measurements.bar(years, data["shots"] - data["hits"], bottom=data["hits"],
                     width=0.73, color=LIGHT, label="Higher energy")
    measurements.set(title="Individual measurements vary", xlabel="Year",
                     ylabel="Measurement count", xlim=adoption.get_xlim(),
                     ylim=(0, data["shots"].max() * 1.22))
    measurements.set_xticks(years[::2])
    measurements.grid(axis="y", color=LIGHT, zorder=0)
    measurements.set_axisbelow(True)
    measurements.legend(loc="upper left", frameon=False, fontsize=9, ncols=2)
    hardest = int(np.argmin(data["hits"] / data["shots"]))
    measurements.annotate(
        f"{years[hardest]}: {data['hits'][hardest]:,} / {data['shots'][hardest]:,}\nminimum-energy outcomes",
        xy=(years[hardest], data["hits"][hardest]), xytext=(0.43, 0.47),
        textcoords="axes fraction", fontsize=9,
        arrowprops={"arrowstyle": "->", "color": AMBER, "lw": 1.5},
        bbox={"facecolor": "white", "edgecolor": "#D5DDE5", "boxstyle": "round,pad=0.5"})

    ordered = sorted(data["industries"], key=lambda name: (data["classical_flips"].get(name, 9999), name))
    positions = np.arange(count)
    missing_year = int(years[-1] + 1)
    q_years = [data["quantum_flips"].get(name, missing_year) for name in ordered]
    c_years = [data["classical_flips"].get(name, missing_year) for name in ordered]
    for position in positions[::2]:
        flips.axhspan(position - 0.5, position + 0.5, color="#F5F7FA", zorder=0)
    flips.scatter(c_years, positions + 0.14, marker="s", s=40, facecolor="white",
                  edgecolor=NAVY, linewidth=1.2, label="Classical exact", zorder=3)
    flips.scatter(q_years, positions - 0.14, marker="o", s=35, color=TEAL,
                  label="Quantum best sample", zorder=4)
    flips.set_yticks(positions, ordered, fontsize=9)
    flips.set(title="Flip year by industry", xlabel="First year digital",
              ylim=(count - 0.4, -0.85))
    earliest, latest = min(q_years + c_years), max(q_years + c_years)
    flips.set_xlim(earliest - 1, latest + 1)
    ticks = list(range(earliest - earliest % 2, latest + 1, 2))
    if missing_year in q_years + c_years and missing_year not in ticks:
        ticks.append(missing_year)
    flips.set_xticks(ticks, ["Not observed" if year == missing_year else str(year) for year in ticks])
    flips.grid(axis="x", color=LIGHT)
    flips.legend(loc="lower left", frameon=True, facecolor="white", edgecolor="none", fontsize=9)

    timing = metadata.get("timing_seconds", {})
    if timing:
        method_label = "quantum simulation workflow" if is_simulation else "quantum workflow"
        fig.text(0.065, 0.075,
                 f"Recorded runtime: {method_label} {timing['quantum_workflow']:.2f} s"
                 f"   |   exact classical minimum cut {timing['classical_min_cut_reference']:.3f} s",
                 fontsize=10, color=NAVY)
    execution_note = ("Ideal quantum-circuit simulation on a classical computer."
                      if is_simulation else "Saved quantum measurements and exact classical reference.")
    fig.text(0.065, 0.04,
             f"Source: {source_name}.  {execution_note}",
             fontsize=8.5, color="#617184")
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quantum", type=Path, default=RESULTS / "quantum_results_twenty_aer_simulator.csv")
    parser.add_argument("--classical", type=Path, default=RESULTS / "twenty_industries_results.csv")
    parser.add_argument("--output-prefix", type=Path, help="output filename without its extension")
    parser.add_argument("--show", action="store_true", help="also open the interactive Matplotlib window")
    args = parser.parse_args()
    if not args.show:
        matplotlib.use("Agg")
    data = load_results(args.quantum, args.classical)
    fig = build_figure(data, args.quantum.name)
    prefix = args.output_prefix or args.quantum.with_name(args.quantum.stem + "_plots")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for extension in (".png", ".pdf", ".svg"):
        destination = prefix.with_suffix(extension)
        fig.savefig(destination, dpi=180, facecolor="white")
        print(f"Saved {destination}")
    import matplotlib.pyplot as plt
    if args.show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
