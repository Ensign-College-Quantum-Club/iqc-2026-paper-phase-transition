"""Check that circuit diagrams and exports preserve the simulated circuit."""

import io
from pathlib import Path
import sys
import unittest

from qiskit import qpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import draw_quantum_circuit as drawing
import quantum_qaoa as quantum


class CircuitDrawingTests(unittest.TestCase):
    def test_overview_preserves_first_middle_and_last_layers(self):
        resistances, ties = quantum.get_network("utah")
        circuit, _ = quantum.build_circuit(resistances, ties, 0.70, 5, 1.0)
        for selected in (1, 3, 5):
            overview, layer, names = drawing.circuit_views(circuit, 5, selected)
            self.assertEqual(overview.decompose(gates_to_decompose=names), circuit)
            self.assertEqual(layer.num_qubits, 5)
            self.assertEqual(layer.num_clbits, 0)
            self.assertNotIn("measure", layer.count_ops())

    def test_full_twenty_qubit_overview_preserves_every_operation(self):
        resistances, ties = quantum.get_network("twenty")
        circuit, _ = quantum.build_circuit(resistances, ties, 0.70, 50, 1.0)
        overview, layer, names = drawing.circuit_views(circuit, 50, 25)
        self.assertEqual(overview.decompose(gates_to_decompose=names), circuit)
        self.assertEqual(dict(layer.count_ops()), {"rz": 44, "cx": 48, "rx": 20})
        self.assertEqual(circuit.count_ops()["measure"], 20)
        self.assertEqual(circuit.size(), 5640)

    def test_qpy_round_trip_preserves_the_full_circuit(self):
        resistances, ties = quantum.get_network("twenty")
        circuit, _ = quantum.build_circuit(resistances, ties, 0.70, 50, 1.0)
        buffer = io.BytesIO()
        qpy.dump(circuit, buffer)
        buffer.seek(0)
        self.assertEqual(qpy.load(buffer)[0], circuit)


if __name__ == "__main__":
    unittest.main()
