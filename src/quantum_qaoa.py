"""Quantum tipping-point map with linear-ramp QAOA (gate-based anneal).

For each year 2026-2040, builds a circuit that slowly ramps from "all
superposed" to the year's Ising energy, measures it, and keeps the
lowest-energy answer. Results are checked against the exact minimum cut.

Same model and sign convention as the challenge README:
    solver form  sum h_i Z_i + sum J_ij Z_i Z_j,   h = -(A - r),  J = -tie
    measured bit 0 -> digital (+1), bit 1 -> paper (-1)

Usage
  Local simulator (free, start here):
      python src/quantum_qaoa.py
      python src/quantum_qaoa.py --network twenty --layers 50
      python src/quantum_qaoa.py --network us1 --layers 50

  qBraid real hardware (spends credits; see --help):
      python src/quantum_qaoa.py --list-devices
      python src/quantum_qaoa.py --device <device id> --layers 3 --shots 500

Networks: twenty (our 20-industry CSVs), utah (5 CSV nodes, default),
us1 (20 nodes with regional shifts and random noise).
Writes per-network CSV results, a text report, and JSON run metadata.
"""

import argparse
import csv
import json
from pathlib import Path
from time import perf_counter, sleep

from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

import scaling_comparison as model
import twenty_industries_over_time as classical

RESULTS = Path(__file__).resolve().parents[1] / "results"


def get_network(name):
    if name == "twenty":
        resistances, ties, _ = classical.load_network(classical.nodes_path,
                                                     classical.connections_path)
        return resistances, ties
    if name == "utah":
        resistances, ties, _ = classical.load_network(
            classical.data_directory / "utah_top10_industry_nodes.csv",
            classical.data_directory / "utah_industry_connections.csv")
        return resistances, ties
    if name == "us1":
        return model.us_network(1)
    raise SystemExit(f"unknown network {name!r} (use twenty, utah or us1)")


def ising_coefficients(resistances, ties, pressure):
    """H = -sum(J Z_i Z_j) - sum((A-r_i) Z_i), with 0=digital, 1=paper."""
    nodes = list(resistances)
    index = {node: i for i, node in enumerate(nodes)}
    fields = [-(pressure - resistances[node]) for node in nodes]
    couplings = [(index[a], index[b], -strength) for a, b, strength in ties]
    return nodes, fields, couplings


def build_cost_hamiltonian(resistances, ties, pressure):
    """Represent the business energy explicitly as a quantum Z/ZZ operator."""
    nodes, fields, couplings = ising_coefficients(resistances, ties, pressure)
    terms = [("Z", [i], field) for i, field in enumerate(fields)]
    terms += [("ZZ", [i, j], value) for i, j, value in couplings]
    return SparsePauliOp.from_sparse_list(terms, num_qubits=len(nodes)), nodes


def build_circuit(resistances, ties, pressure, layers, ramp):
    """Linear-ramp QAOA: cost angle rises 0 -> ramp, mixer angle falls ramp -> 0."""
    nodes, fields, couplings = ising_coefficients(resistances, ties, pressure)
    # Normalise so the largest coefficient is 1; hardware precision is relative.
    scale = max([abs(v) for v in fields] + [abs(j) for _, _, j in couplings] + [1e-9])

    width = len(nodes)
    qc = QuantumCircuit(width, width)
    qc.h(range(width))
    for step in range(1, layers + 1):
        fraction = step / layers
        gamma = ramp * fraction / scale
        beta = ramp * (1 - fraction)
        for i, value in enumerate(fields):
            qc.rz(2 * gamma * value, i)
        for i, j, value in couplings:
            # RZZ written as CNOT-RZ-CNOT so every hardware backend can run it.
            qc.cx(i, j)
            qc.rz(2 * gamma * value, j)
            qc.cx(i, j)
        # Mixer is -sum X, whose lowest state is the |+> start; RX(-2b) = exp(+i b X).
        qc.rx(-2 * beta, range(width))
    qc.measure(range(width), range(width))
    return qc, nodes


def calibration_circuit(width):
    """X on qubit 0 only: tells us which end of the returned bitstring is qubit 0."""
    qc = QuantumCircuit(width, width)
    qc.x(0)
    qc.measure(range(width), range(width))
    return qc


def to_state(bits, nodes, qubit0_on_right):
    bits = bits.replace(" ", "")
    ordered = bits[::-1] if qubit0_on_right else bits
    return {node: (1 if ordered[i] == "0" else -1) for i, node in enumerate(nodes)}


def analyze_counts(counts, nodes, resistances, ties, pressure,
                   qubit0_on_right, exact_energy):
    """Select the lowest-energy observed sample; the reference only scores hits."""
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("The sampler returned no measurements.")
    hits, best, best_energy = 0, None, None
    for bits, count in counts.items():
        if count <= 0:
            continue
        state = to_state(bits, nodes, qubit0_on_right)
        energy = model.energy(state, resistances, ties, pressure)
        if energy <= exact_energy + 1e-9:
            hits += count
        if best_energy is None or energy < best_energy:
            best, best_energy = state, energy
    return best, best_energy, hits, total


def counts_from(result):
    """Read counts from a Qiskit or qBraid result object."""
    for getter in (lambda r: r.data.get_counts(), lambda r: r.get_counts(),
                   lambda r: r.measurement_counts()):
        try:
            counts = getter(result)
            return {str(k): int(v) for k, v in counts.items()}
        except Exception:
            continue
    raise RuntimeError(f"cannot read counts from {type(result).__name__}")


class LocalBackend:
    name = "aer_simulator"

    def __init__(self, seed=1):
        from qiskit import transpile
        from qiskit_aer import AerSimulator
        self.seed = seed
        self.sim = AerSimulator(method="statevector", max_parallel_threads=4,
                                max_parallel_experiments=1)
        self.transpile = transpile

    def run(self, circuits, shots):
        compiled = self.transpile(circuits, self.sim, seed_transpiler=self.seed,
                                  num_processes=1)
        jobs = self.sim.run(compiled, shots=shots, seed_simulator=self.seed)
        result = jobs.result()
        return [result.get_counts(i) for i in range(len(circuits))]


class QbraidBackend:
    def __init__(self, device_id):
        from qbraid.runtime import QbraidProvider
        self.device = QbraidProvider().get_device(device_id)
        self.name = device_id

    def run(self, circuits, shots):
        jobs = [self.device.run(qc, shots=shots) for qc in circuits]
        print(f"  submitted {len(jobs)} jobs to {self.name}; waiting for results...")
        out = []
        for i, job in enumerate(jobs):
            while True:
                status = str(job.status()).upper()
                if "COMPLETED" in status:
                    break
                if any(word in status for word in ("FAILED", "CANCELLED")):
                    raw = job.status()
                    reason = getattr(raw, "status_message", None)
                    try:
                        details = job.metadata()
                    except Exception as error:
                        details = f"(metadata unavailable: {error})"
                    print(f"\n  job {i} id: {job.id}\n  status: {status}\n"
                          f"  reason: {reason}\n  metadata: {details}")
                    # Stop the rest of the batch so a failed run does not keep spending credits.
                    for other in jobs[i + 1:]:
                        try:
                            other.cancel()
                            print(f"  cancelled {other.id}")
                        except Exception as error:
                            print(f"  could not cancel {other.id}: {error}")
                    raise SystemExit(f"job {i} ended with status {status}: {reason}")
                sleep(5)
            out.append(counts_from(job.result()))
            print(f"  job {i + 1}/{len(jobs)} done")
        return out


def list_devices():
    from qbraid.runtime import QbraidProvider
    for device in QbraidProvider().get_devices():
        try:
            qubits = device.num_qubits
        except Exception:
            qubits = "?"
        print(f"{device.id:<40} qubits={qubits!s:<6} status={device.status()}")


def main():
    RESULTS.mkdir(exist_ok=True)
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--network", default="utah", choices=("twenty", "utah", "us1"),
                        help="twenty: our CSV model; utah: 5 CSV nodes; us1: regional/noisy model")
    parser.add_argument("--device", help="qBraid device id; omit for the local simulator")
    parser.add_argument("--list-devices", action="store_true", help="list qBraid devices")
    parser.add_argument("--layers", type=int, default=None,
                        help="ramp steps (default 30 on the simulator, 3 on hardware)")
    parser.add_argument("--ramp", type=float, default=1.0, help="total ramp angle")
    parser.add_argument("--shots", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1, help="reproducible local simulation seed")
    parser.add_argument("--years", default="2026-2040", help="e.g. 2030-2038 to save credits")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    layers = args.layers if args.layers is not None else (3 if args.device else 30)
    if layers < 1 or args.shots < 1 or args.seed < 0:
        parser.error("layers and shots must be positive; seed must be nonnegative")
    if not 0 < args.ramp < float("inf"):
        parser.error("ramp must be finite and positive")
    try:
        first, last = (int(y) for y in args.years.split("-"))
    except ValueError:
        parser.error("years must have the form 2026-2040")
    if first > last:
        parser.error("the first year must not be after the last year")

    workflow_started = perf_counter()
    resistances, ties = get_network(args.network)
    years = list(range(first, last + 1))
    pressures = {y: model.PRESSURE_PER_YEAR * (y - model.YEARS[0]) for y in years}

    backend = QbraidBackend(args.device) if args.device else LocalBackend(seed=args.seed)
    report_lines = []

    def report(line=""):
        print(line, flush=True)
        report_lines.append(line)

    build_started = perf_counter()
    circuits, nodes = [], None
    hamiltonians = {}
    for y in years:
        qc, nodes = build_circuit(resistances, ties, pressures[y], layers, args.ramp)
        circuits.append(qc)
        operator, _ = build_cost_hamiltonian(resistances, ties, pressures[y])
        hamiltonians[str(y)] = [[label, float(value.real)] for label, value in operator.to_list()]
    build_seconds = perf_counter() - build_started
    report(f"{args.network}: {len(nodes)} qubits, {len(years)} years, {layers} layers, "
           f"depth {circuits[0].depth()}, {args.shots} shots each, backend {backend.name}")
    report("Method: fixed linear-ramp quantum circuit (gate-based annealing).")
    report("Encoding: measured 0 = digital (+1); measured 1 = paper (-1).")
    report("Execution: qBraid remote device." if args.device
           else f"Execution: ideal local Aer statevector simulation; seed {args.seed}.")
    if args.device:
        report("  plus 1 calibration circuit (100 shots) to check bit order")
    report("Running quantum circuits...")

    start = perf_counter()
    if args.device:
        all_counts = backend.run(circuits, args.shots)
        cal = backend.run([calibration_circuit(len(nodes))], 100)[0]
        top = max(cal, key=cal.get).replace(" ", "")
        qubit0_on_right = top.endswith("1")
        report(f"  calibration top result {top!r}: qubit 0 is on the "
               f"{'right' if qubit0_on_right else 'left'}")
    else:
        all_counts = backend.run(circuits, args.shots)
        qubit0_on_right = True  # Qiskit convention
    elapsed = perf_counter() - start

    rows, quantum_states, exact_states = [], {}, {}
    reference_seconds = 0.0
    scoring_seconds = 0.0
    report()
    report(f"{'Year':<6}{'Pressure':>9}{'Digital':>9}{'Exact?':>9}"
           f"{'Energy gap':>13}  Ground-state hits / shots")
    for y, counts in zip(years, all_counts):
        A = pressures[y]
        reference_started = perf_counter()
        exact = model.solve_min_cut(resistances, ties, A)
        e_exact = model.energy(exact, resistances, ties, A)
        reference_seconds += perf_counter() - reference_started
        scoring_started = perf_counter()
        best, best_e, hits, total = analyze_counts(
            counts, nodes, resistances, ties, A, qubit0_on_right, e_exact)
        scoring_seconds += perf_counter() - scoring_started
        quantum_states[y], exact_states[y] = best, exact
        matches = best_e <= e_exact + 1e-9
        digital = [n if isinstance(n, str) else n[1] for n in nodes if best[n] == 1]
        energy_gap = max(0.0, best_e - e_exact)
        report(f"{y:<6}{A:>9.2f}{len(digital):>9}{'yes' if matches else 'NO':>9}"
               f"{energy_gap:>13.6f}  {hits}/{total}")
        rows.append({"year": y, "pressure": round(A, 2), "p_exact": hits / total,
                     "best_matches_exact": matches, "best_energy": best_e,
                     "exact_energy": e_exact,
                     "energy_gap": energy_gap, "digital_count": len(digital),
                     "exact_digital_count": sum(spin == 1 for spin in exact.values()),
                     "exact_hits": hits, "shots": total,
                     **{f"quantum_{n}": best[n] for n in nodes}})

    q_flips = model.flip_years(quantum_states)
    e_flips = model.flip_years(exact_states)
    report()
    report(f"{'Node':<28}{'Quantum':>9}{'Exact':>8}")
    for node in nodes:
        mark = "" if q_flips.get(node) == e_flips.get(node) else "  <- differs"
        report(f"{str(node):<28}{q_flips.get(node, '-')!s:>9}{e_flips.get(node, '-')!s:>8}{mark}")
    correct = sum(q_flips.get(n) == e_flips.get(n) for n in nodes)
    mean_p = sum(r["p_exact"] for r in rows) / len(rows)
    quantum_seconds = build_seconds + elapsed + scoring_seconds
    matching_years = sum(row["best_matches_exact"] for row in rows)
    report(f"\nLowest energy matched: {matching_years}/{len(years)} years.")
    report(f"Flip years correct: {correct}/{len(nodes)}.")
    report(f"Mean ground-state sampling frequency: {mean_p:.3f}.")
    report(f"Circuit build: {build_seconds:.3f} s; transpile/execute: {elapsed:.3f} s; "
           f"sample scoring: {scoring_seconds:.3f} s.")
    report(f"Quantum workflow (above stages): {quantum_seconds:.3f} s.")
    report(f"Exact classical minimum-cut reference: {reference_seconds:.3f} s.")

    out = RESULTS / f"quantum_results_{args.network}_{backend.name.replace('/', '_')}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {out.name}")
    summary_path = out.with_suffix(".txt")
    summary_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
    metadata = {
        "network": args.network, "backend": backend.name,
        "execution": "remote device" if args.device else "ideal classical simulation of quantum circuits",
        "nodes": len(nodes), "ties": len(ties), "layers": layers,
        "shots_per_year": args.shots, "seed": args.seed, "ramp": args.ramp,
        "method": "fixed linear-ramp QAOA-style circuit; no variational angle optimization",
        "encoding": {"0": "digital (+1)", "1": "paper (-1)"},
        "input_nodes": [{"node": str(node), "resistance": r} for node, r in resistances.items()],
        "input_ties": [{"from": str(a), "to": str(b), "strength": j} for a, b, j in ties],
        "hamiltonians": hamiltonians,
        "energy_matching_years": matching_years, "years": years,
        "flip_years_matching": correct, "mean_ground_state_frequency": mean_p,
        "timing_seconds": {"circuit_build": build_seconds, "transpile_execute": elapsed,
                           "sample_scoring": scoring_seconds, "quantum_workflow": quantum_seconds,
                           "classical_min_cut_reference": reference_seconds},
    }
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    print(f"Saved {summary_path.name} and {out.with_suffix('.json').name}")


if __name__ == "__main__":
    main()
