"""Verify the quantum encoding, circuit evolution, and classical comparison."""

from itertools import product
from pathlib import Path
import sys
import unittest

import numpy as np
from scipy.linalg import expm
from qiskit.quantum_info import Statevector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import quantum_qaoa as quantum
import scaling_comparison as reference
import twenty_industries_over_time as classical


def direct_energies(resistances, ties, pressure):
    """Score basis states directly, independently of quantum coefficients."""
    nodes = list(resistances)
    energies = []
    for bits in range(2 ** len(nodes)):
        spins = {node: -1 if (bits >> i) & 1 else 1 for i, node in enumerate(nodes)}
        energies.append(-sum(j * spins[a] * spins[b] for a, b, j in ties)
                        - sum((pressure - r) * spins[node] for node, r in resistances.items()))
    return np.array(energies)


class QuantumEncodingTests(unittest.TestCase):
    def test_twenty_network_uses_the_classical_csv_inputs(self):
        resistances, ties = quantum.get_network("twenty")
        expected_r, expected_ties, _ = classical.load_network(
            classical.nodes_path, classical.connections_path)
        self.assertEqual(resistances, expected_r)
        self.assertEqual(ties, expected_ties)
        self.assertEqual((len(resistances), len(ties)), (20, 24))

    def test_single_industry_pressure_and_resistance_signs(self):
        for pressure, expected in [(0.60, [0.15, -0.15]), (0.90, [-0.15, 0.15])]:
            operator, _ = quantum.build_cost_hamiltonian({"Healthcare": 0.75}, [], pressure)
            np.testing.assert_allclose(np.diag(operator.to_matrix()).real, expected, atol=1e-12)

    def test_every_utah_basis_state_matches_the_business_formula(self):
        resistances, ties = quantum.get_network("utah")
        for year in range(2026, 2041):
            pressure = 0.07 * (year - 2026)
            operator, _ = quantum.build_cost_hamiltonian(resistances, ties, pressure)
            matrix = operator.to_matrix()
            expected = direct_energies(resistances, ties, pressure)
            np.testing.assert_allclose(matrix, np.diag(expected), atol=1e-12)

    def test_twenty_qubit_operator_matches_independent_energy_evaluation(self):
        resistances, ties = quantum.get_network("twenty")
        nodes = list(resistances)
        rng = np.random.default_rng(23)
        assignments = [0, 2 ** 20 - 1, int("01" * 10, 2)]
        assignments += [int(value) for value in rng.integers(0, 2 ** 20, size=20)]
        for year in range(2026, 2041):
            pressure = 0.07 * (year - 2026)
            operator, _ = quantum.build_cost_hamiltonian(resistances, ties, pressure)
            self.assertFalse(operator.paulis.x.any())
            for bits in assignments:
                measured_bits = np.array([(bits >> i) & 1 for i in range(20)])
                parities = (operator.paulis.z @ measured_bits) % 2
                quantum_energy = np.dot(operator.coeffs.real, 1 - 2 * parities)
                spins = {node: -1 if measured_bits[i] else 1 for i, node in enumerate(nodes)}
                direct = (-sum(j * spins[a] * spins[b] for a, b, j in ties)
                          - sum((pressure - r) * spins[node] for node, r in resistances.items()))
                self.assertAlmostEqual(float(quantum_energy), direct, places=10)

    def test_cost_layer_applies_the_correct_quantum_phases(self):
        resistances = {"A": 0.20, "B": 0.75, "C": 0.45}
        ties = [("A", "B", 0.15), ("B", "C", 0.09)]
        pressure, ramp = 0.60, 0.80
        circuit, _ = quantum.build_circuit(resistances, ties, pressure, layers=1, ramp=ramp)
        actual = Statevector.from_instruction(circuit.remove_final_measurements(inplace=False)).data
        scale = max([abs(pressure - r) for r in resistances.values()]
                    + [j for _, _, j in ties])
        expected = np.exp(-1j * (ramp / scale) * direct_energies(resistances, ties, pressure)) / np.sqrt(8)
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_cost_and_mixer_layers_match_independent_matrix_evolution(self):
        resistances = {"A": 0.20, "B": 0.75, "C": 0.45}
        ties = [("A", "B", 0.15), ("B", "C", 0.09)]
        pressure, ramp, layers = 0.60, 0.80, 3
        circuit, _ = quantum.build_circuit(resistances, ties, pressure, layers, ramp)
        actual = Statevector.from_instruction(circuit.remove_final_measurements(inplace=False)).data
        scale = max([abs(pressure - r) for r in resistances.values()]
                    + [j for _, _, j in ties])
        cost = direct_energies(resistances, ties, pressure)
        sum_x = np.zeros((8, 8))
        for bits, qubit in product(range(8), range(3)):
            sum_x[bits ^ (1 << qubit), bits] += 1
        expected = np.ones(8, dtype=complex) / np.sqrt(8)
        for step in range(1, layers + 1):
            fraction = step / layers
            expected *= np.exp(-1j * (ramp * fraction / scale) * cost)
            expected = expm(1j * ramp * (1 - fraction) * sum_x) @ expected
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_measurement_bit_order_and_state_encoding(self):
        nodes = ["Insurance", "Healthcare"]
        self.assertEqual(quantum.to_state("10", nodes, True),
                         {"Insurance": 1, "Healthcare": -1})
        self.assertEqual(quantum.to_state("1 0", nodes, False),
                         {"Insurance": -1, "Healthcare": 1})

    def test_best_sample_is_chosen_by_energy_instead_of_frequency(self):
        resistances = {"Insurance": 0.55, "Healthcare": 0.75}
        ties = [("Insurance", "Healthcare", 0.15)]
        best, energy, hits, total = quantum.analyze_counts(
            {"10": 990, "00": 10}, list(resistances), resistances, ties, 0.70, True, -0.25)
        self.assertEqual(best, {"Insurance": 1, "Healthcare": 1})
        self.assertAlmostEqual(energy, -0.25)
        self.assertEqual((hits, total), (10, 1000))

    def test_missing_the_optimum_is_reported_without_classical_correction(self):
        resistances = {"Insurance": 0.55, "Healthcare": 0.75}
        ties = [("Insurance", "Healthcare", 0.15)]
        best, energy, hits, total = quantum.analyze_counts(
            {"10": 1000}, list(resistances), resistances, ties, 0.70, True, -0.25)
        self.assertEqual(best, {"Insurance": 1, "Healthcare": -1})
        self.assertAlmostEqual(energy, -0.05)
        self.assertAlmostEqual(energy - (-0.25), 0.20)
        self.assertEqual((hits, total), (0, 1000))

    def test_empty_measurements_are_rejected(self):
        with self.assertRaises(ValueError):
            quantum.analyze_counts({}, ["A"], {"A": 0.50}, [], 0.60, True, -0.10)

    def test_aer_measurements_calibrate_qubit_zero(self):
        backend = quantum.LocalBackend(seed=7)
        counts = backend.run([quantum.calibration_circuit(3)], shots=128)
        self.assertEqual(counts, [{"001": 128}])

    def test_exact_min_cut_matches_exhaustive_search_for_all_fifteen_years(self):
        resistances, ties = quantum.get_network("twenty")
        nodes, states, fixed, totals = classical.prepare_arrangements(resistances, ties)
        for year in range(2026, 2041):
            pressure = 0.07 * (year - 2026)
            labels, exact_energy = classical.solve_year(pressure, states, fixed, totals)
            min_cut = reference.solve_min_cut(resistances, ties, pressure)
            self.assertAlmostEqual(reference.energy(min_cut, resistances, ties, pressure),
                                   exact_energy, places=10)
            for node, label in zip(nodes, labels):
                if label != "Either":
                    self.assertEqual(min_cut[node], 1 if label == "Digital" else -1)


if __name__ == "__main__":
    unittest.main()
