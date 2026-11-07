"""Animate yearly minimum-energy states of the 20-industry Ising model.

Run: python src/animate_paper_phase_transition.py
Add --show for a year slider and Play/Pause controls.
Use --show --no-save to explore without regenerating the animation files.
"""

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import matplotlib
import numpy as np

import draw_ising_network as network
import twenty_industries_over_time as model

PAPER = "#F4EBDD"
DIGITAL = "#007F78"
GOLD = "#DEA321"
MIXED = "#BA6148"


def compute_frames(resistances, ties):
    """Solve every year independently, choosing an actual minimum-energy state."""
    nodes, states, fixed, totals = model.prepare_arrangements(resistances, ties)
    frames, ever_digital = [], set()
    for year in range(model.start_year, model.end_year + 1):
        pressure = model.pressure_per_year * (year - model.start_year)
        energies = fixed - pressure * totals
        winner = int(np.argmin(energies))
        spins = {node: int(states[winner, i]) for i, node in enumerate(nodes)}
        digital = {node for node, spin in spins.items() if spin == 1}
        newly = [node for node in nodes if node in digital and node not in ever_digital]
        ever_digital.update(digital)
        frames.append({"year": year, "pressure": pressure, "states": spins,
                       "energy": float(energies[winner]), "digital_count": len(digital),
                       "mean_spin": sum(spins.values()) / len(spins), "newly_digital": newly})
    return frames


def build_view(resistances, ties, frames):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig = network.build_figure(resistances, ties)
    ax = fig.axes[0]
    patches = {artist.get_gid(): artist for artist in ax.patches if artist.get_gid()}
    labels = {artist.get_gid(): artist for artist in ax.texts if artist.get_gid()}
    fig.texts[1].set_text("The paper-to-digital phase transition")
    status = fig.texts[2]
    fig.texts[3].set_text("")
    fig.texts[5].set_text(
        "Each frame is that year's exact minimum-energy arrangement. "
        "Pressure A(y) = 0.07(y - 2026); mean spin = sum(s_i) / 20. "
        "The animation loops back to 2026.")
    newly_label = fig.text(0.05, 0.194, "", fontsize=9.4, color="#25374A")
    fig.legend(handles=[Patch(facecolor=PAPER, edgecolor="#9F7751", label="Paper: s = -1"),
                        Patch(facecolor=DIGITAL, edgecolor=DIGITAL, label="Digital: s = +1"),
                        Patch(facecolor=DIGITAL, edgecolor=GOLD, linewidth=2.5, label="Newly digital this year"),
                        Line2D([0], [0], color=MIXED, linestyle="--", linewidth=2,
                               label="Partners in different states")],
               loc="lower left", bbox_to_anchor=(0.045, 0.141), ncols=4,
               frameon=False, fontsize=9.2)

    def update(index):
        frame = frames[int(index)]
        new = set(frame["newly_digital"])
        for industry, resistance in resistances.items():
            key = industry.replace(" ", "_")
            spin = frame["states"][industry]
            digital = spin == 1
            patch = patches["node_" + key]
            patch.set_facecolor(DIGITAL if digital else PAPER)
            patch.set_edgecolor(GOLD if industry in new else "#005B56" if digital else "#9F7751")
            patch.set_linewidth(3.4 if industry in new else 1.5)
            labels["name_" + key].set_color("white" if digital else "#46392E")
            detail = labels["resistance_" + key]
            detail.set_text(f"s = {spin:+d}   r = {resistance:.2f}")
            detail.set_fontsize(8.7)
            detail.set_color("#D9EFEB" if digital else "#786755")
        for first, second, _ in ties:
            edge = patches["edge_" + first.replace(" ", "_") + "__" + second.replace(" ", "_")]
            a, b = frame["states"][first], frame["states"][second]
            mixed = a != b
            edge.set_color(MIXED if mixed else "#4A9893" if a == 1 else "#B5A38D")
            edge.set_linestyle("--" if mixed else "-")
        status.set_text(
            f"Year {frame['year']}   |   AI pressure A = {frame['pressure']:.2f}   |   "
            f"Digital {frame['digital_count']}/{len(resistances)}   |   "
            f"Mean spin = {frame['mean_spin']:+.2f}   |   Minimum energy = {frame['energy']:.2f}")
        newly_label.set_text("Newly digital: " + (", ".join(frame["newly_digital"]) or "None this year"))
        return list(patches.values()) + list(labels.values()) + [status, newly_label]

    update(0)
    return fig, update


def add_controls(fig, update, frames, fps):
    from matplotlib.widgets import Button, Slider

    slider = Slider(fig.add_axes((0.13, 0.006, 0.62, 0.018)), "Year",
                    frames[0]["year"], frames[-1]["year"],
                    valinit=frames[0]["year"], valstep=1, valfmt="%0.0f", color=DIGITAL)
    button = Button(fig.add_axes((0.80, 0.004, 0.10, 0.027)), "Play")
    timer = fig.canvas.new_timer(interval=1000 / fps)
    playing = False

    def choose_year(year):
        update(int(year) - frames[0]["year"])
        fig.canvas.draw_idle()

    def next_year():
        index = (int(slider.val) - frames[0]["year"] + 1) % len(frames)
        slider.set_val(frames[index]["year"])

    def toggle(_):
        nonlocal playing
        playing = not playing
        button.label.set_text("Pause" if playing else "Play")
        timer.start() if playing else timer.stop()
        fig.canvas.draw_idle()

    slider.on_changed(choose_year)
    button.on_clicked(toggle)
    timer.add_callback(next_year)
    fig.canvas.mpl_connect("close_event", lambda _: timer.stop())
    return slider, button, timer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="open the interactive year slider")
    parser.add_argument("--no-save", action="store_true", help="skip file exports; requires --show")
    parser.add_argument("--fps", type=float, default=1.0, help="animation years per second")
    args = parser.parse_args()
    if not 0 < args.fps < float("inf"):
        parser.error("fps must be positive and finite")
    if args.no_save and not args.show:
        parser.error("--no-save requires --show")
    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    resistances, ties, _ = model.load_network(model.nodes_path, model.connections_path)
    frames = compute_frames(resistances, ties)
    fig, update = build_view(resistances, ties, frames)
    if not args.no_save:
        from matplotlib.animation import FuncAnimation, PillowWriter
        from matplotlib.backends.backend_pdf import PdfPages

        output = ROOT / "results"
        output.mkdir(exist_ok=True)
        jumps = [frames[i]["digital_count"] - frames[i - 1]["digital_count"]
                 if i else 0 for i in range(len(frames))]
        tipping = int(np.argmax(jumps))
        snapshots = sorted({0, max(0, tipping - 1), tipping})
        with PdfPages(output / "paper_phase_transition_snapshots.pdf") as pdf:
            for index in snapshots:
                update(index)
                path = output / f"paper_phase_transition_{frames[index]['year']}.png"
                fig.savefig(path, dpi=160, facecolor="white")
                pdf.savefig(fig, facecolor="white")
                print(f"Saved {path}", flush=True)
        sequence = list(range(len(frames))) + [len(frames) - 1] * 2
        animation = FuncAnimation(fig, update, frames=sequence, interval=1000 / args.fps,
                                  blit=False, repeat=True)
        gif_path = output / "paper_phase_transition.gif"
        print("Rendering the yearly Ising network animation...", flush=True)
        animation.save(gif_path, writer=PillowWriter(fps=args.fps), dpi=90)
        metadata = {"model": "20-industry ferromagnetic Ising ground states",
                    "method": "exact enumeration at each year's pressure",
                    "ties": len(ties), "nodes": len(resistances),
                    "tie_policy": "first enumerated minimum if energies tie",
                    "frames": frames}
        (output / "paper_phase_transition_frames.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Saved {gif_path}", flush=True)
        print(f"Biggest tipping year: {frames[tipping]['year']} ({jumps[tipping]} newly digital).")

    if args.show:
        update(0)
        controls = add_controls(fig, update, frames, args.fps)
        plt.show()
        controls[2].stop()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
