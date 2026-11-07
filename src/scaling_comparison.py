"""Scaling comparison: how solve time and accuracy grow with network size.

Solves the same Ising model with three classical methods, for every year
2026-2040, on networks of growing size:

  brute force         - checks every arrangement (exact, exponential; n <= 20)
  minimum cut         - exact for any size, because every tie is positive
  simulated annealing - the classical stand-in for a quantum annealer

Networks: the 5-node Utah model, then the README's 20 industries copied across
1, 2, 3, 6 and 12 U.S. regions (20-240 nodes), then larger synthetic grids of
regions (480-1920 nodes) to push the scaling further.

Each region shifts resistance by up to +/-0.15, each node adds a little noise
(seeded, so runs repeat), and the same industry in neighbouring regions is tied
with J = 0.05, as the challenge README suggests.

Run with: python src/scaling_comparison.py
Writes: results/scaling_results.csv, results/scaling.png
"""

import csv
from pathlib import Path
from time import perf_counter

import networkx as nx
import numpy as np

RESULTS = Path(__file__).resolve().parents[1] / "results"
YEARS = range(2026, 2041)
PRESSURE_PER_YEAR = 0.07
TIE_SCALE = 0.15
NEIGHBOUR_TIE = 0.05
REGION_SHIFT = 0.15
NODE_NOISE = 0.02
SA_READS = 50

RESISTANCES = {
    "Technology": 0.10, "Media": 0.20, "Telecom": 0.25, "Retail": 0.30,
    "Hospitality": 0.35, "Logistics": 0.40, "Banking": 0.45, "Accounting": 0.50,
    "Manufacturing": 0.50, "Insurance": 0.55, "Energy": 0.55, "Pharma": 0.60,
    "Education": 0.60, "Nonprofit": 0.65, "Real Estate": 0.65,
    "Construction": 0.70, "Agriculture": 0.70, "Healthcare": 0.75,
    "Government": 0.85, "Legal": 0.90,
}
PARTNER_STRENGTHS = [
    ("Healthcare", "Insurance", 1.0), ("Manufacturing", "Logistics", 0.9),
    ("Banking", "Real Estate", 0.8), ("Retail", "Logistics", 0.8),
    ("Construction", "Real Estate", 0.8), ("Healthcare", "Pharma", 0.7),
    ("Legal", "Real Estate", 0.7), ("Healthcare", "Government", 0.6),
    ("Legal", "Government", 0.6), ("Accounting", "Banking", 0.6),
    ("Government", "Education", 0.6), ("Agriculture", "Logistics", 0.6),
    ("Telecom", "Technology", 0.6), ("Insurance", "Banking", 0.5),
    ("Legal", "Banking", 0.5), ("Energy", "Manufacturing", 0.5),
    ("Technology", "Media", 0.5), ("Insurance", "Legal", 0.4),
    ("Accounting", "Nonprofit", 0.4), ("Construction", "Government", 0.4),
    ("Hospitality", "Retail", 0.4), ("Pharma", "Logistics", 0.4),
    ("Nonprofit", "Education", 0.4), ("Media", "Retail", 0.3),
]

# Twelve U.S. regions and which ones border each other.
REGIONS = ["Pacific NW", "California", "Mountain West", "Southwest", "Texas",
           "Plains", "Midwest", "Great Lakes", "Southeast", "Florida",
           "Mid-Atlantic", "New England"]
REGION_BORDERS = [
    ("Pacific NW", "California"), ("Pacific NW", "Mountain West"),
    ("California", "Mountain West"), ("California", "Southwest"),
    ("Mountain West", "Southwest"), ("Mountain West", "Plains"),
    ("Southwest", "Texas"), ("Texas", "Plains"), ("Texas", "Southeast"),
    ("Plains", "Midwest"), ("Midwest", "Great Lakes"), ("Midwest", "Southeast"),
    ("Great Lakes", "Mid-Atlantic"), ("Southeast", "Florida"),
    ("Southeast", "Mid-Atlantic"), ("Mid-Atlantic", "New England"),
]

UTAH_RESISTANCES = {"Healthcare": 0.75, "Education": 0.60, "Government": 0.85,
                    "Retail": 0.30, "Manufacturing": 0.50}
UTAH_TIES = [("Healthcare", "Government", 0.09), ("Government", "Education", 0.09)]


def utah_network():
    return dict(UTAH_RESISTANCES), list(UTAH_TIES)


def regional_network(regions, borders, seed=7):
    """README industries copied into each region, with partner and neighbour ties."""
    rng = np.random.default_rng(seed)
    resistances, ties = {}, []
    for region in regions:
        shift = rng.uniform(-REGION_SHIFT, REGION_SHIFT)
        for industry, base in RESISTANCES.items():
            resistances[(region, industry)] = base + shift + rng.normal(0, NODE_NOISE)
        for a, b, strength in PARTNER_STRENGTHS:
            ties.append(((region, a), (region, b), TIE_SCALE * strength))
    for r1, r2 in borders:
        for industry in RESISTANCES:
            ties.append(((r1, industry), (r2, industry), NEIGHBOUR_TIE))
    return resistances, ties


def us_network(region_count):
    regions = REGIONS[:region_count]
    borders = [(a, b) for a, b in REGION_BORDERS if a in regions and b in regions]
    return regional_network(regions, borders)


def grid_network(rows, cols):
    """Synthetic regions on a grid, each bordering its four neighbours."""
    regions = [f"R{r}-{c}" for r in range(rows) for c in range(cols)]
    borders = [(f"R{r}-{c}", f"R{r}-{c + 1}") for r in range(rows) for c in range(cols - 1)]
    borders += [(f"R{r}-{c}", f"R{r + 1}-{c}") for r in range(rows - 1) for c in range(cols)]
    return regional_network(regions, borders)


def energy(state, resistances, ties, pressure):
    """README energy: -sum J s_i s_j - sum (A - r_i) s_i."""
    return (-sum(j * state[a] * state[b] for a, b, j in ties)
            - sum((pressure - r) * state[n] for n, r in resistances.items()))


def solve_brute_force(resistances, ties, pressure):
    nodes = list(resistances)
    index = {n: i for i, n in enumerate(nodes)}
    count = len(nodes)
    numbers = np.arange(2 ** count, dtype=np.uint32)
    states = np.empty((2 ** count, count), dtype=np.int8)
    for i in range(count):
        states[:, i] = 2 * ((numbers >> i) & 1).astype(np.int8) - 1
    field = pressure - np.array([resistances[n] for n in nodes])
    energies = -(states @ field)
    for a, b, j in ties:
        energies -= j * states[:, index[a]] * states[:, index[b]]
    best = states[int(np.argmin(energies))]
    return {n: int(best[index[n]]) for n in nodes}


def solve_min_cut(resistances, ties, pressure):
    """Exact ground state: the Digital side of the cheapest Digital/Paper split."""
    graph = nx.DiGraph()
    graph.add_node("DIGITAL")
    graph.add_node("PAPER")
    for node, r in resistances.items():
        h = pressure - r
        graph.add_node(node)
        if h > 0:
            graph.add_edge("DIGITAL", node, capacity=2 * h)
        elif h < 0:
            graph.add_edge(node, "PAPER", capacity=-2 * h)
    for a, b, j in ties:
        for u, v in ((a, b), (b, a)):
            if graph.has_edge(u, v):
                graph[u][v]["capacity"] += 2 * j
            else:
                graph.add_edge(u, v, capacity=2 * j)
    _, (digital_side, _) = nx.minimum_cut(graph, "DIGITAL", "PAPER")
    return {n: (1 if n in digital_side else -1) for n in resistances}


def solve_annealing(resistances, ties, pressure, sampler):
    # Solver sign convention from the README: h = -(A - r), J = -tie.
    h = {n: -(pressure - r) for n, r in resistances.items()}
    J = {}
    for a, b, j in ties:
        J[(a, b)] = J.get((a, b), 0.0) - j
    result = sampler.sample_ising(h, J, num_reads=SA_READS, seed=11)
    return dict(result.first.sample)


def flip_years(states_by_year):
    years = {}
    for year, state in states_by_year.items():
        for node, spin in state.items():
            if spin == 1:
                years.setdefault(node, year)
    return years


def run(label, resistances, ties, sampler):
    n = len(resistances)
    print(f"{label:<28} {n:>5} nodes  {len(ties):>5} ties", flush=True)
    row = {"network": label, "nodes": n, "ties": len(ties)}
    pressures = {y: PRESSURE_PER_YEAR * (y - YEARS[0]) for y in YEARS}

    methods = [("min_cut", solve_min_cut)]
    if n <= 20:
        methods.append(("brute_force", solve_brute_force))
    methods.append(("annealing", lambda r, t, p: solve_annealing(r, t, p, sampler)))

    results = {}
    for name, solver in methods:
        start = perf_counter()
        results[name] = {y: solver(resistances, ties, pressures[y]) for y in YEARS}
        row[f"{name}_seconds"] = perf_counter() - start

    exact = results["min_cut"]
    if "brute_force" in results:
        # Sanity check: both exact methods must find the same lowest energy.
        for y in YEARS:
            e_cut = energy(exact[y], resistances, ties, pressures[y])
            e_bf = energy(results["brute_force"][y], resistances, ties, pressures[y])
            assert abs(e_cut - e_bf) < 1e-9, f"exact methods disagree in {y}"

    sa = results["annealing"]
    correct = sum(sa[y][node] == exact[y][node] for y in YEARS for node in resistances)
    row["annealing_node_years_correct_pct"] = 100 * correct / (n * len(YEARS))
    exact_flips, sa_flips = flip_years(exact), flip_years(sa)
    row["annealing_flip_years_correct_pct"] = 100 * sum(
        exact_flips.get(node) == sa_flips.get(node) for node in resistances) / n
    row["annealing_years_at_ground_energy"] = sum(
        energy(sa[y], resistances, ties, pressures[y])
        <= energy(exact[y], resistances, ties, pressures[y]) + 1e-9 for y in YEARS)
    return row


def plot(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colours = {"brute_force": "#2a78d6", "min_cut": "#eb6834", "annealing": "#1baf7a"}
    names = {"brute_force": "Brute force (exact)", "min_cut": "Minimum cut (exact)",
             "annealing": "Simulated annealing"}

    fig, ax = plt.subplots(figsize=(9, 5.2), facecolor=surface)
    ax.set_facecolor(surface)
    for key in ("brute_force", "min_cut", "annealing"):
        pts = [(r["nodes"], r[f"{key}_seconds"]) for r in rows if f"{key}_seconds" in r]
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=colours[key], linewidth=2, marker="o", markersize=7,
                markeredgecolor=surface, markeredgewidth=2, label=names[key])
        ax.annotate(names[key], (xs[-1], ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=ink, fontsize=10)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Nodes in the network", color=muted)
    ax.set_ylabel("Seconds to solve all 15 years", color=muted)
    ax.set_title("Solve time as the network grows", color=ink, loc="left",
                 fontsize=14, pad=12)
    ax.grid(True, which="major", color=grid, linewidth=0.8)
    ax.tick_params(colors=muted)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(grid)
    ax.legend(frameon=False, loc="lower right", labelcolor=ink)
    bf = [r for r in rows if "brute_force_seconds" in r]
    if bf:
        # Brute force doubles with every extra node; project it to 40 nodes.
        last = bf[-1]
        days = last["brute_force_seconds"] * 2 ** (40 - last["nodes"]) / 86400
        ax.annotate(f"40 nodes by brute force:\n~{days:,.0f} days (projected)",
                    (last["nodes"], last["brute_force_seconds"]), xytext=(-14, 30),
                    textcoords="offset points", ha="right", color=muted, fontsize=9,
                    arrowprops=dict(arrowstyle="-", color=muted, lw=0.8))
    ax.set_xlim(right=max(r["nodes"] for r in rows) * 6)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=surface)


def main():
    RESULTS.mkdir(exist_ok=True)
    import neal
    sampler = neal.SimulatedAnnealingSampler()
    networks = [("Utah (5 industries)", *utah_network())]
    for count in (1, 2, 3, 6, 12):
        networks.append((f"US, {count} region{'s' if count > 1 else ''}",
                         *us_network(count)))
    for rows, cols in ((4, 6), (6, 8), (8, 12)):
        networks.append((f"Synthetic {rows}x{cols} regions", *grid_network(rows, cols)))

    rows = [run(label, r, t, sampler) for label, r, t in networks]

    with (RESULTS / "scaling_results.csv").open("w", newline="") as f:
        fieldnames = list(dict.fromkeys(k for r in rows for k in r))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    plot(rows, RESULTS / "scaling.png")

    print(f"\n{'Network':<28}{'Nodes':>6}{'Brute':>10}{'Min-cut':>10}{'Anneal':>10}"
          f"{'SA flip yrs OK':>16}{'SA exact yrs':>14}")
    for r in rows:
        bf = f"{r['brute_force_seconds']:.3f}" if "brute_force_seconds" in r else "-"
        print(f"{r['network']:<28}{r['nodes']:>6}{bf:>10}{r['min_cut_seconds']:>10.3f}"
              f"{r['annealing_seconds']:>10.3f}"
              f"{r['annealing_flip_years_correct_pct']:>15.1f}%"
              f"{r['annealing_years_at_ground_energy']:>11}/15")


if __name__ == "__main__":
    main()
