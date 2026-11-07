# Utah Paper-to-Digital Phase Transition

This project applies the Ising-model challenge from the **IQC 2026 Paper Phase Transition** README to a small network of Utah industries. It uses the challenge's suggested baseline resistances and partner-tie values, plus Utah sources that document selected employers and public-sector relationships.

The results below are outputs of this specified model. They are not measured adoption rates or a forecast validated against Utah company behavior.

## Repository layout

```
data/       model inputs
src/        solvers and scripts
results/    solver outputs (CSV) and charts
sources/    PDF copies of the sources cited below
```

**Data**

- [`data/utah_top10_industry_nodes.csv`](data/utah_top10_industry_nodes.csv): five Utah industry nodes, representative employers, DWS industry categories and employment ranges, and resistance values.
- [`data/utah_industry_connections.csv`](data/utah_industry_connections.csv): the two modeled ties, README strengths and coefficients, and Utah evidence for the relationships.
- [`data/twenty_industry_nodes.csv`](data/twenty_industry_nodes.csv) and [`data/twenty_industry_connections.csv`](data/twenty_industry_connections.csv): the original challenge's 20 suggested industries and 24 ties.

**Scripts**

| Script | What it does | Output |
|---|---|---|
| [`src/two_industries.py`](src/two_industries.py) | Insurance and Healthcare: every paper/digital combination | printed |
| [`src/two_industries_over_time.py`](src/two_industries_over_time.py) | Insurance and Healthcare, solved for each year 2026 to 2040 | printed |
| [`src/twenty_industries_over_time.py`](src/twenty_industries_over_time.py) | Exact flip years from the 20-industry CSVs; `--utah` selects the five-industry Utah CSVs | Per-model results CSV and text summary in `results/` |
| [`src/scaling_comparison.py`](src/scaling_comparison.py) | Brute force vs minimum cut vs simulated annealing, 5 to 1,920 nodes | `results/scaling_results.csv`, `results/scaling.png` |
| [`src/quantum_qaoa.py`](src/quantum_qaoa.py) | Quantum tipping-point map (fixed linear-ramp circuit) on the Aer simulator or qBraid hardware | Per-network CSV, text report, and JSON metadata in `results/` |
| [`src/plot_quantum_results.py`](src/plot_quantum_results.py) | Matplotlib figure comparing adoption, flip years, and quantum measurement counts | PNG, PDF, and SVG in `results/` |
| [`src/draw_quantum_circuit.py`](src/draw_quantum_circuit.py) | Matplotlib drawings of the actual Qiskit circuit plus a fresh single-year Aer run | Circuit diagrams, histogram, QPY/OpenQASM, and measurement CSV in `results/` |
| [`src/draw_ising_network.py`](src/draw_ising_network.py) | Diagram of all 20 industry spins, resistances, and 24 labeled ties | `results/ising_industry_network.png`, `.pdf`, `.svg` |
| [`src/animate_paper_phase_transition.py`](src/animate_paper_phase_transition.py) | Animated annual Ising ground states, with optional year slider and Play/Pause controls | `results/paper_phase_transition.gif`, snapshots, and frame data |

The classical runner prints the number of digital industries each year and saves the same table and first digital year for each industry:

- Original 20-industry model: [`results/twenty_industries_results.csv`](results/twenty_industries_results.csv) and [`results/twenty_industries_summary.txt`](results/twenty_industries_summary.txt).
- Five-industry Utah model: [`results/utah_industries_results.csv`](results/utah_industries_results.csv) and `results/utah_industries_summary.txt` (generated when run).

**Run**

```bash
pip install -r requirements.txt
python src/twenty_industries_over_time.py
python src/twenty_industries_over_time.py --utah
python src/scaling_comparison.py
python src/quantum_qaoa.py                    # simulator, Utah network
python src/quantum_qaoa.py --network twenty --layers 50 --shots 1000 --seed 1
python src/quantum_qaoa.py --list-devices     # qBraid devices
```

Input paths are relative to the repository, so scripts can be launched from another working directory. Each classical model writes its own output files.

The quantum `twenty` option loads exactly the same 20-industry CSVs as the classical runner. The `utah` option loads the five-industry Utah CSVs. The existing `us1` option adds seeded regional shifts and noise, so it represents a separate model.

For the encoding used by the quantum script, measured `0` means digital (`s=+1`) and measured `1` means paper (`s=-1`). The circuit implements the cost Hamiltonian `H = -sum(J_ij Z_i Z_j) - sum((A-r_i) Z_i)`. Its cost and mixer angles follow a fixed ramp; this implementation does not optimize variational angles.

The quantum CSV records the best sampled energy, the exact minimum-cut reference energy, their gap, digital counts, and ground-state hit counts. The text report includes flip-year comparisons and timing; JSON metadata records the input network, raw Hamiltonian terms, run settings, and timings. Simulator timings describe quantum-circuit simulation on a classical computer.

The project-local environment used for the simulator run can be invoked on Windows with:

```bash
.venv/Scripts/python.exe src/quantum_qaoa.py --network twenty --layers 50 --shots 1000 --seed 1
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe src/plot_quantum_results.py --show
.venv/Scripts/python.exe src/draw_quantum_circuit.py --year 2036 --layers 50 --shots 1000
.venv/Scripts/python.exe src/draw_ising_network.py --show
.venv/Scripts/python.exe src/animate_paper_phase_transition.py --show --no-save
```

The tests independently verify Hamiltonian energies, cost and mixer evolution, measurement bit order, sample selection, and agreement between minimum cut and exhaustive search.

The plotting script reads the saved 20-industry quantum and classical CSVs without rerunning the simulation. It writes `results/quantum_results_twenty_aer_simulator_plots.png`, `.pdf`, and `.svg`; `--show` also opens the Matplotlib window. Its adoption and measurement axes show counts. The runtime labels come from the saved run metadata.

The circuit drawing script calls the same `build_circuit` function as the quantum runner. Its default 2036 example saves a [grouped full-circuit overview](results/circuit_twenty_2036_overview.pdf), [expanded layer 25](results/circuit_twenty_2036_layer25.pdf), and [Aer measurement histogram](results/circuit_twenty_2036_measurements.png). The overview expands back into the exact original circuit. Full executable circuit exports are saved as QPY and OpenQASM; a separate CSV maps qubit indices to industries. The expanded middle layer's incoming wires are left unlabeled because they carry the state prepared by earlier layers.

The histogram comes from a new single-year Aer experiment. Its seeded measurement counts can differ from a multi-year batch even when the circuit and seed match. These files have their own names and preserve the saved yearly comparison results.

The [Ising network diagram](results/ising_industry_network.pdf) reads the 20-industry input CSVs. Each node shows an industry and its resistance; each undirected edge shows its positive coupling coefficient, with thicker lines for stronger ties. The schematic layout avoids crossed connections and does not represent geography.

The [paper phase transition animation](results/paper_phase_transition.gif) shows the exact minimum-energy arrangement for each year from 2026 to 2040. Cream nodes are paper (`s=-1`), teal nodes are digital (`s=+1`), and gold borders identify first-time digital adopters that year. Dashed edges join partners in different states. The display includes pressure, minimum energy, digital count, and mean spin. It visualizes annual optimization results rather than time evolution inside the quantum circuit.

Run `python src/animate_paper_phase_transition.py` to regenerate the GIF, [three snapshot slides](results/paper_phase_transition_snapshots.pdf), and `results/paper_phase_transition_frames.json`. Add `--show --no-save` to explore with the year slider without regenerating files. Each frame is solved on the same 20-industry CSV model; if minima tie, the first enumerated minimum is shown.

## Data and modeling choices

### Nodes and representative employers

The Utah Department of Workforce Services (DWS) major-employer data was used to identify ten representative employers. Those employers are grouped into five model nodes, one per industry in Utah:

| Model industry | Representative employers | Resistance, \(r_i\) |
|---|---|---:|
| Healthcare | Intermountain Health Care | 0.75 |
| Education | University of Utah; Brigham Young University; Davis County School District; Utah State University | 0.60 |
| Government | State of Utah; Hill Air Force Base | 0.85 |
| Retail | Walmart; Smith's Food & Drug | 0.30 |
| Manufacturing | Northrop Grumman Corp. | 0.50 |

These are **industry nodes**, not ten separate company nodes. The employers help identify which Utah industries to include; the model itself describes industries in one region.

### Resistance values

The resistance values are the challenge README's suggested base values for Healthcare, Education, Government, Retail, and Manufacturing. We use those base values directly, without adding regional shifts or random noise. This keeps the baseline transparent and reproducible, but it does not make the values Utah-specific measurements.

### Partner ties and Utah evidence

The challenge README supplies a strength of 0.60 for both Healthcare–Government and Government–Education. Since the model includes only five selected industries, these are the only two listed README ties whose endpoints are both present. The README's suggested scaling is \(J_{ij}=0.15\times\text{tie strength}\), so each modeled tie has \(J=0.09\).

| Tie | README strength | Model \(J_{ij}\) | External Utah evidence |
|---|---:|---:|---|
| Healthcare–Government | 0.60 | 0.09 | Utah's FY2025 Medicaid spending report lists state Department of Health and Human Services spending and University of Utah Hospitals & Clinics funding. It also states: “The Department oversees Medicaid expenditures and reimburses providers for medical services.” |
| Government–Education | 0.60 | 0.09 | Utah's FY2026 budget lists appropriations for Education and Higher Education. |

The external sources support the existence of public-sector relationships. **They do not determine the numerical tie strengths**; those come from the challenge README. Retail and Manufacturing have no listed tie to another included node, so they are isolated in this five-node network.

## Model

Each industry is in one of two states: paper \(s_i=-1\) or digital \(s_i=+1\). AI pressure starts at zero in 2026 and increases by 0.07 per year:

\[
A(y)=0.07(y-2026).
\]

For each year, the model selects the state configuration with the lowest energy:

\[
E(y)=-\sum_{(i,j)}J_{ij}s_is_j-\sum_i\bigl(A(y)-r_i\bigr)s_i.
\]

With two ties, both with \(J=0.09\), the Utah energy expression is:

\[
E(y)=-0.09s_{Healthcare}s_{Government}-0.09s_{Government}s_{Education}-\sum_i\bigl(A(y)-r_i\bigr)s_i.
\]

For a solver using the conventional minimization form with a positive quadratic term \(Q_{ij}s_is_j\), use \(Q_{ij}=-0.09\) for both ties. The linear field is \(h_i=-(A(y)-r_i)\), following the sign convention described in the challenge README.

## Baseline results

The exact classical baseline was calculated by checking all \(2^5=32\) paper/digital configurations at each year from 2026 through 2040 and selecting the minimum-energy state. The first year an industry is digital is its flip year.

| Industry | Flip year | AI pressure in flip year |
|---|---:|---:|
| Retail | 2031 | 0.35 |
| Manufacturing | 2034 | 0.56 |
| Education | 2036 | 0.70 |
| Healthcare | 2037 | 0.77 |
| Government | 2037 | 0.77 |

| Year(s) | Industries in the digital state |
|---|---|
| 2026–2030 | None |
| 2031–2033 | Retail |
| 2034–2035 | Retail, Manufacturing |
| 2036 | Retail, Manufacturing, Education |
| 2037–2040 | Healthcare, Government, Education, Retail, Manufacturing |

In this model, Retail and Manufacturing cross their thresholds first because they have lower base resistance and no modeled partner ties. Education follows in 2036. Healthcare and Government switch together in 2037, producing the largest one-year change in the network. The connections help determine the collective switch of the connected three-industry group.

## Interpretation and limitations

- These are model outputs under the stated assumptions, not verified dates when Utah employers will stop using paper.
- Resistance values are challenge-suggested industry baselines, not Utah-specific measurements.
- The Utah sources document relationships and public funding, but do not measure tie strength. Both numeric tie strengths are taken from the challenge README.
- The five-node network contains only two ties. Retail and Manufacturing are isolated because no listed challenge tie links them to another included industry.
- The classical result is exact for this five-node model. A quantum solver or simulator must be run on the same model to make the challenge's quantum/classical comparison; no quantum advantage is claimed here.

## Sources

1. **Challenge model and suggested values:** [The Paper Phase Transition — IQC 2026 README](https://github.com/PrinterLogic/iqc-2026-paper-phase-transition). Source for the Ising energy expression, suggested base resistances, tie strengths, tie scaling, AI-pressure schedule, and solver sign convention.
2. **Utah employers and industry categories:** [Utah Department of Workforce Services — Major Employers by County](https://jobs.utah.gov/wi/data/library/firm/majoremployers.html). Used to identify representative Utah employers and their reported industry/employment categories ([local copy](sources/largest-employers.pdf)).
3. **Healthcare–Government evidence:** [Utah Medicaid Spending Statewide report (PDF)](https://le.utah.gov/interim/2026/pdf/00000583.pdf) ([local copy](sources/healthcare-government.pdf)), especially PDF pages 1 and 3. Supports the state Medicaid/provider relationship; it does not set the tie's numeric weight.
4. **Government–Education evidence:** [Utah FY2026 State Budget, Table 3](https://le.utah.gov/CobiServlet/cobi/BudgetRD?key=stateBudget) ([local copy](sources/government-education.pdf)), printed page 1-14. Lists Education and Higher Education appropriations; it does not set the tie's numeric weight.

