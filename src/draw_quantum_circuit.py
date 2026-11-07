"""Draw the actual Qiskit circuit with Matplotlib and sample it with Aer.

Run: python src/draw_quantum_circuit.py
Defaults: our 20 CSV industries, year 2036, 50 layers, 1000 shots.
"""

import argparse
import csv
import json
import os
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import matplotlib
from qiskit import QuantumCircuit, qasm3, qpy

import quantum_qaoa as quantum


def circuit_views(circuit, layers, selected_layer):
    """Group actual instructions for display, preserving the full circuit."""
    width = circuit.num_qubits
    instructions = list(circuit.data)
    prefix, suffix = instructions[:width], instructions[-width:]
    body = instructions[width:-width]
    if not 1 <= selected_layer <= layers or len(body) % layers:
        raise ValueError("Select a valid layer from the circuit's repeated ramp.")
    if not all(item.operation.name == "h" for item in prefix):
        raise ValueError("The circuit must begin with its Hadamard preparation.")
    if not all(item.operation.name == "measure" for item in suffix):
        raise ValueError("The circuit must end with its measurements.")
    per_layer = len(body) // layers

    def section(first, last, name):
        part = QuantumCircuit(width, name=name)
        for instruction in body[(first - 1) * per_layer:last * per_layer]:
            if instruction.clbits:
                raise ValueError("A cost/mixer layer unexpectedly contains classical bits.")
            part.append(instruction.operation,
                        [circuit.find_bit(bit).index for bit in instruction.qubits])
        return part

    overview = QuantumCircuit(width, width, global_phase=circuit.global_phase)
    for instruction in prefix:
        overview.append(instruction.operation,
                        [circuit.find_bit(bit).index for bit in instruction.qubits])
    block_names = []

    def add_block(first, last, label):
        name = f"layers_{first}_{last}"
        part = section(first, last, name)
        overview.append(part.to_instruction(label=label), range(width))
        block_names.append(name)

    if selected_layer > 1:
        add_block(1, selected_layer - 1, f"Layers 1-{selected_layer - 1}")
    add_block(selected_layer, selected_layer, f"Layer {selected_layer}\nCost + mixer")
    if selected_layer < layers:
        add_block(selected_layer + 1, layers, f"Layers {selected_layer + 1}-{layers}")
    for instruction in suffix:
        overview.append(instruction.operation,
                        [circuit.find_bit(bit).index for bit in instruction.qubits],
                        [circuit.find_bit(bit).index for bit in instruction.clbits])
    expanded = section(selected_layer, selected_layer, f"layer_{selected_layer}")
    return overview, expanded, block_names


def save_circuit_figure(circuit, destination, title, fold, initial_state=True):
    import matplotlib.pyplot as plt

    figure = circuit.draw(output="mpl", style="iqp", fold=fold,
                          initial_state=initial_state, cregbundle=True, scale=0.7)
    figure.suptitle(title, fontsize=14, y=1.01)
    # Keep raster exports manageable; PDF retains every gate as a vector.
    dpi = min(150, 6500 / max(figure.get_size_inches()))
    for extension in (".png", ".pdf"):
        path = destination.with_suffix(extension)
        figure.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.25,
                       facecolor="white")
        print(f"Saved {path}", flush=True)
    plt.close(figure)


def save_histogram(counts, nodes, resistances, ties, pressure, exact_energy,
                   destination, title):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    displayed = ranked[:10]
    labels = [bits for bits, _ in displayed]
    values = [count for _, count in displayed]
    colors = []
    for bits, _ in displayed:
        state = quantum.to_state(bits, nodes, True)
        energy = quantum.model.energy(state, resistances, ties, pressure)
        colors.append("#008579" if energy <= exact_energy + 1e-9 else "#718299")
    remainder = sum(count for _, count in ranked[10:])
    if remainder:
        labels.append("Other measured states")
        values.append(remainder)
        colors.append("#DCE3EA")

    fig, ax = plt.subplots(figsize=(13, 7.5))
    fig.subplots_adjust(left=0.25, right=0.94, top=0.80, bottom=0.18)
    bars = ax.barh(labels, values, color=colors, height=0.68)
    ax.invert_yaxis()
    ax.bar_label(bars, padding=5, fontsize=10)
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_xlabel(f"Measurement count (out of {sum(counts.values()):,})", fontsize=11)
    ax.set_ylabel("Measured bitstring (highest qubit index on the left)", fontsize=10)
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(axis="x", color="#E8EDF2")
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(handles=[Patch(color="#008579", label="Minimum-energy state"),
                       Patch(color="#718299", label="Higher-energy displayed state")],
              loc="lower right", frameon=False, fontsize=9)
    fig.suptitle(title, fontsize=19, weight="bold", y=0.96)
    fig.text(0.25, 0.865, "Qiskit Aer simulation | Ten most frequent states, plus remaining outcomes",
             fontsize=10, color="#617184")
    fig.text(0.25, 0.085,
             f"Encoding: 0 = digital (+1), 1 = paper (-1). Exact minimum energy: {exact_energy:.4f}.",
             fontsize=10)
    for extension in (".png", ".pdf"):
        path = destination.with_suffix(extension)
        fig.savefig(path, dpi=180, facecolor="white")
        print(f"Saved {path}", flush=True)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", choices=("twenty", "utah", "us1"), default="twenty")
    parser.add_argument("--year", type=int, default=2036)
    parser.add_argument("--layers", type=int, default=50)
    parser.add_argument("--layer", type=int, help="layer to expand; defaults to the middle layer")
    parser.add_argument("--shots", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ramp", type=float, default=1.0)
    args = parser.parse_args()
    if args.layers < 1 or args.shots < 1 or args.seed < 0:
        parser.error("layers and shots must be positive; seed must be nonnegative")
    selected_layer = args.layer if args.layer is not None else (args.layers + 1) // 2
    if not 1 <= selected_layer <= args.layers:
        parser.error("layer must be between 1 and the total layer count")
    if not 0 < args.ramp < float("inf"):
        parser.error("ramp must be positive and finite")
    matplotlib.use("Agg")

    resistances, ties = quantum.get_network(args.network)
    pressure = quantum.model.PRESSURE_PER_YEAR * (args.year - quantum.model.YEARS[0])
    circuit, nodes = quantum.build_circuit(resistances, ties, pressure, args.layers, args.ramp)
    overview, expanded, block_names = circuit_views(circuit, args.layers, selected_layer)
    # This is a regrouping of the actual circuit, not a different algorithm.
    if overview.decompose(gates_to_decompose=block_names) != circuit:
        raise RuntimeError("The diagram overview no longer matches the original circuit.")
    results = quantum.RESULTS
    results.mkdir(exist_ok=True)
    prefix = results / f"circuit_{args.network}_{args.year}"

    with prefix.with_suffix(".qpy").open("wb") as output:
        qpy.dump(circuit, output)
    prefix.with_suffix(".qasm").write_text(qasm3.dumps(circuit), encoding="utf-8", newline="\n")
    with prefix.with_name(prefix.name + "_qubits.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["qubit_index", "industry", "bit_0", "bit_1"])
        writer.writerows((i, str(node), "Digital", "Paper") for i, node in enumerate(nodes))

    title = f"{args.network}: {len(nodes)} qubits, {args.layers} layers | Year {args.year}, pressure {pressure:.2f}"
    print(f"Drawing {title}", flush=True)
    save_circuit_figure(overview, prefix.with_name(prefix.name + "_overview"),
                        title + "\nFull circuit with grouped cost/mixer layers", fold=-1)
    save_circuit_figure(expanded, prefix.with_name(prefix.name + f"_layer{selected_layer}"),
                        f"Expanded layer {selected_layer} of {args.layers} | Year {args.year}\n"
                        "Actual RZ, CX-RZ-CX, and RX operations from quantum_qaoa.py",
                        fold=45, initial_state=False)

    print(f"Running the full circuit in Aer with {args.shots:,} shots...", flush=True)
    started = perf_counter()
    counts = quantum.LocalBackend(seed=args.seed).run([circuit], args.shots)[0]
    elapsed = perf_counter() - started
    exact = quantum.model.solve_min_cut(resistances, ties, pressure)
    exact_energy = quantum.model.energy(exact, resistances, ties, pressure)
    best, best_energy, hits, total = quantum.analyze_counts(
        counts, nodes, resistances, ties, pressure, True, exact_energy)

    with prefix.with_name(prefix.name + "_counts.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["bitstring", "count", "energy", "minimum_energy"])
        for bits, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            state = quantum.to_state(bits, nodes, True)
            energy = quantum.model.energy(state, resistances, ties, pressure)
            writer.writerow([bits, count, energy, energy <= exact_energy + 1e-9])
    save_histogram(counts, nodes, resistances, ties, pressure, exact_energy,
                   prefix.with_name(prefix.name + "_measurements"),
                   f"Aer measurements of the {len(nodes)}-qubit circuit | {args.year}")
    metadata = {"network": args.network, "year": args.year, "pressure": pressure,
                "qubits": len(nodes), "layers": args.layers, "expanded_layer": selected_layer,
                "shots": total, "seed": args.seed, "backend": "aer_simulator",
                "depth": circuit.depth(), "gate_counts": dict(circuit.count_ops()),
                "ground_state_hits": hits, "best_energy": best_energy,
                "exact_energy": exact_energy, "digital_count": sum(spin == 1 for spin in best.values()),
                "transpile_and_simulate_seconds": elapsed,
                "overview_expands_to_original": True,
                "measurement_note": "A separate single-year experiment; seeded counts can differ from a multi-year batch."}
    prefix.with_name(prefix.name + "_summary.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Aer: {hits}/{total} minimum-energy measurements; best energy {best_energy:.6f}; "
          f"exact {exact_energy:.6f}; {elapsed:.3f} seconds.")
    print(f"Full executable circuit saved as {prefix.with_suffix('.qpy').name} and .qasm")


if __name__ == "__main__":
    main()
