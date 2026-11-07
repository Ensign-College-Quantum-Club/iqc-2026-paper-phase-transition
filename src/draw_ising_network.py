"""Draw the 20-industry Ising network directly from the model input CSVs.

Run: python src/draw_ising_network.py
Add --show to open the Matplotlib window.
"""

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import matplotlib

import twenty_industries_over_time as model


# Schematic positions spread out the connected network without crossing edges.
# Connections and weights are always read from the CSVs, not from this layout.
POSITIONS = {
    "Technology": (-3.5, -6.8),
    "Media": (-8.0, -6.8),
    "Telecom": (0.5, -6.8),
    "Retail": (-8.0, -2.0),
    "Hospitality": (-12.5, -2.0),
    "Logistics": (-8.0, 2.6),
    "Banking": (4.8, -5.3),
    "Accounting": (10.0, -5.3),
    "Manufacturing": (-8.0, 6.8),
    "Insurance": (0.2, -2.6),
    "Energy": (-3.8, 6.8),
    "Pharma": (-4.0, 2.6),
    "Education": (13.5, 2.6),
    "Nonprofit": (13.5, -2.6),
    "Real Estate": (8.0, -2.4),
    "Construction": (8.5, 1.8),
    "Agriculture": (-12.5, 2.6),
    "Healthcare": (0.2, 2.6),
    "Government": (7.5, 5.0),
    "Legal": (4.5, 0.1),
}


def build_figure(resistances, ties):
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    if set(resistances) != set(POSITIONS):
        raise ValueError("This layout expects the original 20-industry CSV model.")
    fig = plt.figure(figsize=(18, 11.5), facecolor="white")
    ax = fig.add_axes((0.025, 0.20, 0.95, 0.62))
    ax.set_xlim(-14.5, 15.5)
    ax.set_ylim(-8.2, 8.2)
    ax.set_axis_off()
    navy = "#25374A"
    teal = "#17646B"
    fig.text(0.05, 0.955, f"ONE REGION  /  {len(resistances)} INDUSTRIES  /  {len(ties)} CONNECTIONS",
             fontsize=11, color=teal, weight="bold")
    fig.text(0.05, 0.905, "The Ising industry network", fontsize=27, color=navy, weight="bold")
    fig.text(0.05, 0.86,
             "One spin per industry: paper (s = -1) or digital (s = +1). Connected partners favor matching states.",
             fontsize=11.5, color="#617184")

    patches = {}
    for industry, resistance in resistances.items():
        x, y = POSITIONS[industry]
        patch = FancyBboxPatch((x - 1.40, y - 0.64), 2.80, 1.28,
                               boxstyle="round,pad=0.08,rounding_size=0.18",
                               facecolor="#F3F8F9", edgecolor=teal, linewidth=1.5,
                               zorder=3)
        ax.add_patch(patch)
        patch.set_gid("node_" + industry.replace(" ", "_"))
        patches[industry] = patch
        ax.text(x, y + 0.17, industry, ha="center", va="center", fontsize=10.3,
                color=navy, weight="bold", zorder=4,
                gid="name_" + industry.replace(" ", "_"))
        ax.text(x, y - 0.29, f"r = {resistance:.2f}", ha="center", va="center",
                fontsize=9.2, color="#617184", zorder=4,
                gid="resistance_" + industry.replace(" ", "_"))

    for first, second, strength in ties:
        first_pos, second_pos = POSITIONS[first], POSITIONS[second]
        edge = FancyArrowPatch(first_pos, second_pos,
                               patchA=patches[first], patchB=patches[second],
                               arrowstyle="-", connectionstyle="arc3,rad=0",
                               shrinkA=3, shrinkB=3,
                               linewidth=1.1 + 2.8 * strength / 0.15,
                               color="#56858D", zorder=1)
        ax.add_patch(edge)
        edge.set_gid("edge_" + first.replace(" ", "_") + "__" + second.replace(" ", "_"))
        middle = ((first_pos[0] + second_pos[0]) / 2,
                  (first_pos[1] + second_pos[1]) / 2)
        ax.text(*middle, f"{strength:.3f}", ha="center", va="center", fontsize=9.0,
                color=navy, zorder=5,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 2.5})

    fig.text(0.05, 0.158,
             "NODE LABEL: resistance r     |     EDGE LABEL: coupling J_ij     |     Thicker line = stronger tie",
             fontsize=10, color=navy)
    fig.text(0.05, 0.092,
             r"$E(\mathbf{s},y)=-\sum_{(i,j)\in\mathcal{E}}J_{ij}s_i s_j"
             r"-\sum_i[A(y)-r_i]s_i$",
             fontsize=18, color=navy)
    fig.text(0.05, 0.038,
             "Challenge-suggested baseline values. Schematic layout; positions are not geographic. "
             "Each undirected tie is shown once; J_ii = 0.",
             fontsize=9.2, color="#617184")
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="also open the Matplotlib window")
    args = parser.parse_args()
    if not args.show:
        matplotlib.use("Agg")
    resistances, ties, _ = model.load_network(model.nodes_path, model.connections_path)
    figure = build_figure(resistances, ties)
    prefix = ROOT / "results" / "ising_industry_network"
    prefix.parent.mkdir(exist_ok=True)
    for extension in (".png", ".pdf", ".svg"):
        path = prefix.with_suffix(extension)
        figure.savefig(path, dpi=180, facecolor="white")
        print(f"Saved {path}")
    import matplotlib.pyplot as plt
    if args.show:
        plt.show()
    else:
        plt.close(figure)


if __name__ == "__main__":
    main()
