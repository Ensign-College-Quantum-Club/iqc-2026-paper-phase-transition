"""Find flip years using industry and connection CSV files.

This classical solver checks every arrangement using NumPy. It is intended
for this small learning example; enumeration grows exponentially with nodes.
The number of industries and their resistances and ties come from the CSVs.

Run with: python src/twenty_industries_over_time.py
For the five-industry Utah model, add: --utah
"""

import argparse
import csv
from pathlib import Path
from time import perf_counter

import numpy as np


repository_directory = Path(__file__).resolve().parents[1]
data_directory = repository_directory / "data"
results_directory = repository_directory / "results"
nodes_path = data_directory / "twenty_industry_nodes.csv"
connections_path = data_directory / "twenty_industry_connections.csv"
start_year = 2026
end_year = 2040
pressure_per_year = 0.07


def load_network(nodes_path, connections_path):
    """Read resistances and match connection endpoints using CSV node IDs."""
    resistances = {}
    industry_by_id = {}
    regions = set()
    with nodes_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            node_id = row["Node_ID"].strip()
            industry = row["Model_Industry"].strip()
            resistance = float(row["Resistance_r"])
            if not node_id or not industry:
                raise ValueError("Each node needs a Node_ID and Model_Industry.")
            if node_id in industry_by_id or industry in resistances:
                raise ValueError(f"Duplicate node ID or industry: {node_id}, {industry}")
            if not 0 <= resistance <= 1:
                raise ValueError(f"Resistance must be between 0 and 1: {industry}")
            industry_by_id[node_id] = industry
            resistances[industry] = resistance
            regions.add(row["Region"].strip())
    if not resistances:
        raise ValueError("The industry CSV has no nodes.")

    ties = []
    seen_edges = set()
    with connections_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            first_id = row["From_Node"].strip()
            second_id = row["To_Node"].strip()
            if first_id not in industry_by_id or second_id not in industry_by_id:
                raise ValueError(f"Connection references an unknown node: {first_id}, {second_id}")
            edge = frozenset((first_id, second_id))
            if first_id == second_id or edge in seen_edges:
                raise ValueError(f"Self-connection or duplicate tie: {first_id}, {second_id}")
            # This column already contains J = 0.15 * raw strength.
            strength = float(row["README_J_Coefficient"])
            if not np.isfinite(strength) or strength < 0:
                raise ValueError("Tie coefficients must be finite and nonnegative.")
            ties.append((industry_by_id[first_id], industry_by_id[second_id], strength))
            seen_edges.add(edge)
    return resistances, ties, ", ".join(sorted(regions))


def prepare_arrangements(resistances, ties):
    """List every arrangement and calculate the part of energy fixed over time."""
    industries = list(resistances)
    indices = {industry: index for index, industry in enumerate(industries)}
    arrangement_count = 2 ** len(industries)
    numbers = np.arange(arrangement_count, dtype=np.uint32)
    states = np.empty((arrangement_count, len(industries)), dtype=np.int8)

    # Each bit represents one industry's choice: 0 -> paper, 1 -> digital.
    for index in range(len(industries)):
        states[:, index] = 2 * ((numbers >> index) & 1).astype(np.int8) - 1

    # E = -sum(J*s_i*s_j) + sum(r_i*s_i) - pressure*sum(s_i).
    # Only the final term changes each year, so reuse the other terms.
    fixed_energy = states @ np.array(list(resistances.values()), dtype=float)
    for first, second, strength in ties:
        fixed_energy -= strength * states[:, indices[first]] * states[:, indices[second]]
    spin_totals = states.sum(axis=1, dtype=np.int32)
    return industries, states, fixed_energy, spin_totals


def solve_year(pressure, states, fixed_energy, spin_totals):
    """Return each industry's state, preserving ambiguity in equal-energy answers."""
    energies = fixed_energy - pressure * spin_totals
    lowest_energy = float(energies.min())
    winners = states[np.isclose(energies, lowest_energy, rtol=0.0, atol=1e-9)]
    labels = []
    for index in range(states.shape[1]):
        if np.all(winners[:, index] == 1):
            labels.append("Digital")
        elif np.all(winners[:, index] == -1):
            labels.append("Paper")
        else:
            labels.append("Either")
    return labels, lowest_energy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utah", action="store_true",
                        help="Run the five-industry Utah model instead of the original 20 industries.")
    arguments = parser.parse_args()
    selected_nodes = data_directory / "utah_top10_industry_nodes.csv" if arguments.utah else nodes_path
    selected_connections = data_directory / "utah_industry_connections.csv" if arguments.utah else connections_path

    started = perf_counter()
    resistances, ties, region = load_network(selected_nodes, selected_connections)
    industries, states, fixed_energy, spin_totals = prepare_arrangements(resistances, ties)
    flip_years = {industry: None for industry in industries}
    rows = []
    found_tie = False
    summary_lines = []

    def print_summary(line=""):
        """Keep the saved table identical to the table printed in the terminal."""
        print(line)
        summary_lines.append(line)

    print(f"{region}: {len(industries)} industries, {len(ties)} partner ties.")
    print(f"Method: classical exhaustive search over {len(states):,} arrangements.")
    print(f"Inputs: {selected_nodes.name} and {selected_connections.name}.\n")
    print_summary(f"{'Year':<6} {'Pressure':>8} {'Digital':>8}  Newly digital")

    for year in range(start_year, end_year + 1):
        pressure = pressure_per_year * (year - start_year)
        labels, lowest_energy = solve_year(pressure, states, fixed_energy, spin_totals)
        newly_digital = []
        for industry, label in zip(industries, labels):
            if label == "Digital" and flip_years[industry] is None:
                flip_years[industry] = year
                newly_digital.append(industry)
            found_tie = found_tie or label == "Either"
            rows.append({"year": year, "pressure": round(pressure, 2),
                         "industry": industry, "state": label,
                         "lowest_energy": round(lowest_energy, 10)})

        digital_count = labels.count("Digital")
        print_summary(f"{year:<6} {pressure:>8.2f} {digital_count:>8}  "
                      f"{', '.join(newly_digital) or '-'}")

    elapsed = perf_counter() - started
    print_summary()
    print_summary("First definite digital year:")
    for industry, year in sorted(flip_years.items(), key=lambda item: (item[1] or 9999, item[0])):
        print_summary(f"{industry:<16} {year if year is not None else 'Not reached'}")
    if found_tie:
        print_summary("Either means equally good arrangements disagree on that industry.")
        print_summary("Flip years require all lowest-energy arrangements to agree on digital.")
    print(f"\nPreparation and yearly solving: {elapsed:.3f} seconds (includes console output).")

    results_directory.mkdir(exist_ok=True)
    results_filename = "utah_industries_results.csv" if arguments.utah else "twenty_industries_results.csv"
    output_path = results_directory / results_filename
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Yearly states saved to: {output_path}")

    summary_filename = "utah_industries_summary.txt" if arguments.utah else "twenty_industries_summary.txt"
    summary_path = results_directory / summary_filename
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Yearly table and flip years saved to: {summary_path}")


if __name__ == "__main__":
    main()
