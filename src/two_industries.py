"""Check every paper/digital combination for Insurance and Healthcare.

Run with: python src/two_industries.py
"""

from itertools import product
from math import isclose


# Inputs from our worked example. Change these to explore the model.
pressure = 0.70
insurance_resistance = 0.55
healthcare_resistance = 0.75
tie_strength = 0.15

PAPER = -1
DIGITAL = +1


def state_name(state):
    return "Digital" if state == DIGITAL else "Paper"


print(f"Pressure: {pressure:.2f}")
print(f"Resistance: Insurance = {insurance_resistance:.2f}, "
      f"Healthcare = {healthcare_resistance:.2f}")
print(f"Tie strength: {tie_strength:.2f}\n")
print(f"{'Insurance':<12} {'Healthcare':<12} {'Insurance E':>12} "
      f"{'Healthcare E':>13} {'Tie E':>8} {'Total E':>9}")

results = []

# Two choices for each industry give four combinations in total.
for insurance_state, healthcare_state in product((PAPER, DIGITAL), repeat=2):
    # Each industry's own preference: -(pressure - resistance) * state.
    insurance_energy = -(pressure - insurance_resistance) * insurance_state
    healthcare_energy = -(pressure - healthcare_resistance) * healthcare_state

    # Relationship preference: matching states lower this score.
    tie_energy = -tie_strength * insurance_state * healthcare_state

    total_energy = insurance_energy + healthcare_energy + tie_energy
    results.append((total_energy, insurance_state, healthcare_state))

    print(f"{state_name(insurance_state):<12} "
          f"{state_name(healthcare_state):<12} "
          f"{insurance_energy:>+12.2f} {healthcare_energy:>+13.2f} "
          f"{tie_energy:>+8.2f} {total_energy:>+9.2f}")

# Report every minimum, including ties within floating-point rounding.
lowest_energy = min(result[0] for result in results)
print(f"\nLowest energy: {lowest_energy:+.2f}")
for energy, insurance_state, healthcare_state in results:
    if isclose(energy, lowest_energy, rel_tol=0.0, abs_tol=1e-9):
        print(f"Best arrangement: Insurance = {state_name(insurance_state)}, "
              f"Healthcare = {state_name(healthcare_state)}")
