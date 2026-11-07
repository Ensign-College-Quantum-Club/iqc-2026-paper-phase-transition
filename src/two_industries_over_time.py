"""Solve the same two-industry model once per year, from 2026 to 2040.

Run with: python src/two_industries_over_time.py
"""

from itertools import product
from math import isclose


# Keep these inputs fixed while pressure increases each year.
insurance_resistance = 0.55
healthcare_resistance = 0.75
tie_strength = 0.15
pressure_per_year = 0.07
start_year = 2026
end_year = 2040

PAPER = -1
DIGITAL = +1


def solve_year(pressure, tie_strength):
    """Check all four arrangements and return every lowest-energy answer."""
    results = []
    for insurance_state, healthcare_state in product((PAPER, DIGITAL), repeat=2):
        insurance_energy = -(pressure - insurance_resistance) * insurance_state
        healthcare_energy = -(pressure - healthcare_resistance) * healthcare_state
        tie_energy = -tie_strength * insurance_state * healthcare_state
        total_energy = insurance_energy + healthcare_energy + tie_energy
        results.append((total_energy, insurance_state, healthcare_state))

    lowest_energy = min(result[0] for result in results)
    best_states = []
    for energy, insurance_state, healthcare_state in results:
        if isclose(energy, lowest_energy, rel_tol=0.0, abs_tol=1e-9):
            best_states.append((insurance_state, healthcare_state))
    return best_states, lowest_energy


def state_label(states):
    """Show Either if equally good arrangements disagree on this industry."""
    if all(state == DIGITAL for state in states):
        return "Digital"
    if all(state == PAPER for state in states):
        return "Paper"
    return "Either"


def main():
    insurance_flip_year = None
    healthcare_flip_year = None
    found_tie = False

    print(f"Tie strength: {tie_strength:.2f}")
    print(f"Pressure starts at 0 and increases by {pressure_per_year:.2f} per year.\n")
    print(f"{'Year':<6} {'Pressure':>8} {'Insurance':>12} "
          f"{'Healthcare':>12} {'Lowest E':>10}")

    # The new step: repeat our four-combination calculation for each year.
    for year in range(start_year, end_year + 1):
        pressure = pressure_per_year * (year - start_year)
        best_states, lowest_energy = solve_year(pressure, tie_strength)

        insurance = state_label([states[0] for states in best_states])
        healthcare = state_label([states[1] for states in best_states])
        if insurance == "Either" or healthcare == "Either":
            found_tie = True

        # Record the first year digital is the unambiguous best state.
        if insurance == "Digital" and insurance_flip_year is None:
            insurance_flip_year = year
        if healthcare == "Digital" and healthcare_flip_year is None:
            healthcare_flip_year = year

        print(f"{year:<6} {pressure:>8.2f} {insurance:>12} "
              f"{healthcare:>12} {lowest_energy:>+10.2f}")

    print("\nFirst digital years:")
    print(f"Insurance: {insurance_flip_year if insurance_flip_year is not None else 'Not reached'}")
    print(f"Healthcare: {healthcare_flip_year if healthcare_flip_year is not None else 'Not reached'}")
    if found_tie:
        print("Either means paper and digital both occur in lowest-energy answers.")
        print("Reported flip years require every lowest-energy answer to agree on digital.")


if __name__ == "__main__":
    main()
