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
      python src/quantum_qaoa.py --network us1 --layers 50

  qBraid real hardware (spends credits; see --help):
      python src/quantum_qaoa.py --list-devices
      python src/quantum_qaoa.py --device <device id> --layers 3 --shots 500

Networks: utah (5 nodes, default), us1 (20 nodes, one US region).
Writes results/quantum_results_<network>_<backend>.csv
"""

import argparse
import csv
from pathlib import Path
from time import perf_counter, sleep

from qiskit import QuantumCircuit

import scaling_comparison as model

RESULTS = Path(__file__).resolve().parents[1] / "results"


def get_network(name):
    if name == "utah":
        return model.utah_network()
    if name == "us1":
        return model.us_network(1)
    raise SystemExit(f"unknown network {name!r} (use utah or us1)")


def build_circuit(resistances, ties, pressure, layers, ramp):
    """Linear-ramp QAOA: cost angle rises 0 -> ramp, mixer angle falls ramp -> 0."""
    nodes = list(resistances)
    index = {node: i for i, node in enumerate(nodes)}
    h = {node: -(pressure - r) for node, r in resistances.items()}
    J = [(index[a], index[b], -strength) for a, b, strength in ties]
    # Normalise so the largest coefficient is 1; hardware precision is relative.
    scale = max([abs(v) for v in h.values()] + [abs(j) for _, _, j in J] + [1e-9])

    width = len(nodes)
    qc = QuantumCircuit(width, width)
    qc.h(range(width))
    for step in range(1, layers + 1):
        fraction = step / layers
        gamma = ramp * fraction / scale
        beta = ramp * (1 - fraction)
        for node, value in h.items():
            qc.rz(2 * gamma * value, index[node])
        for i, j, value in J:
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

    def __init__(self):
        from qiskit import transpile
        from qiskit_aer import AerSimulator
        self.sim = AerSimulator(method="statevector")
        self.transpile = transpile

    def run(self, circuits, shots):
        jobs = self.sim.run(self.transpile(circuits, self.sim), shots=shots,
                            seed_simulator=1)
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
    parser.add_argument("--network", default="utah", help="utah (5 nodes) or us1 (20 nodes)")
    parser.add_argument("--device", help="qBraid device id; omit for the local simulator")
    parser.add_argument("--list-devices", action="store_true", help="list qBraid devices")
    parser.add_argument("--layers", type=int, default=None,
                        help="ramp steps (default 30 on the simulator, 3 on hardware)")
    parser.add_argument("--ramp", type=float, default=1.0, help="total ramp angle")
    parser.add_argument("--shots", type=int, default=1000)
    parser.add_argument("--years", default="2026-2040", help="e.g. 2030-2038 to save credits")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    resistances, ties = get_network(args.network)
    layers = args.layers or (3 if args.device else 30)
    first, last = (int(y) for y in args.years.split("-"))
    years = list(range(first, last + 1))
    pressures = {y: model.PRESSURE_PER_YEAR * (y - model.YEARS[0]) for y in years}

    backend = QbraidBackend(args.device) if args.device else LocalBackend()
    circuits, nodes = [], None
    for y in years:
        qc, nodes = build_circuit(resistances, ties, pressures[y], layers, args.ramp)
        circuits.append(qc)
    print(f"{args.network}: {len(nodes)} qubits, {len(years)} years, {layers} layers, "
          f"depth {circuits[0].depth()}, {args.shots} shots each, backend {backend.name}")
    if args.device:
        print(f"  plus 1 calibration circuit (100 shots) to check bit order")

    start = perf_counter()
    if args.device:
        all_counts = backend.run(circuits, args.shots)
        cal = backend.run([calibration_circuit(len(nodes))], 100)[0]
        top = max(cal, key=cal.get).replace(" ", "")
        qubit0_on_right = top.endswith("1")
        print(f"  calibration top result {top!r}: qubit 0 is on the "
              f"{'right' if qubit0_on_right else 'left'}")
    else:
        all_counts = backend.run(circuits, args.shots)
        qubit0_on_right = True  # Qiskit convention
    elapsed = perf_counter() - start

    rows, quantum_states, exact_states = [], {}, {}
    print(f"\n{'Year':<6}{'P(exact)':>10}{'Best = exact':>14}  Digital (quantum best)")
    for y, counts in zip(years, all_counts):
        A = pressures[y]
        exact = model.solve_min_cut(resistances, ties, A)
        e_exact = model.energy(exact, resistances, ties, A)
        total = sum(counts.values())
        hits, best, best_e = 0, None, None
        for bits, c in counts.items():
            state = to_state(bits, nodes, qubit0_on_right)
            e = model.energy(state, resistances, ties, A)
            if e <= e_exact + 1e-9:
                hits += c
            if best_e is None or e < best_e:
                best, best_e = state, e
        quantum_states[y], exact_states[y] = best, exact
        matches = best_e <= e_exact + 1e-9
        digital = [n if isinstance(n, str) else n[1] for n in nodes if best[n] == 1]
        print(f"{y:<6}{hits / total:>10.3f}{'yes' if matches else 'NO':>14}  "
              f"{', '.join(digital) or '-'}")
        rows.append({"year": y, "pressure": round(A, 2), "p_exact": hits / total,
                     "best_matches_exact": matches, "best_energy": best_e,
                     "exact_energy": e_exact,
                     **{f"quantum_{n}": best[n] for n in nodes}})

    q_flips = model.flip_years(quantum_states)
    e_flips = model.flip_years(exact_states)
    print(f"\n{'Node':<28}{'Quantum':>9}{'Exact':>8}")
    for node in nodes:
        mark = "" if q_flips.get(node) == e_flips.get(node) else "  <- differs"
        print(f"{str(node):<28}{q_flips.get(node, '-')!s:>9}{e_flips.get(node, '-')!s:>8}{mark}")
    correct = sum(q_flips.get(n) == e_flips.get(n) for n in nodes)
    mean_p = sum(r["p_exact"] for r in rows) / len(rows)
    print(f"\nFlip years correct: {correct}/{len(nodes)}.  "
          f"Wall time incl. queue: {elapsed:.1f} s")
    print(f"Mean P(exact) per shot: {mean_p:.3f}  vs random guessing "
          f"1/2^{len(nodes)} = {1 / 2 ** len(nodes):.4f}  "
          f"({mean_p * 2 ** len(nodes):.0f}x better than chance)")

    out = RESULTS / f"quantum_results_{args.network}_{backend.name.replace('/', '_')}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {out.name}")


if __name__ == "__main__":
    main()
