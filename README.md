# Warehouse Picker Route Optimizer

A decision-support prototype for the supplied synthetic five-aisle warehouse.
It combines product-location selection, a Pyomo/HiGHS MIP routing benchmark,
three aisle-routing heuristics, and a Streamlit comparison/visualization.

## Run locally

From this directory, install the dependencies and start the app:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens in a browser. Select `ORD001` or `ORD002`, compare the MIP with
Return, Traversal, and Largest Gap, then select a strategy to view its pick
locations, visit sequence, route, and travel distance.

Run the command-line MIP or automated tests with:

```powershell
python solve_mip.py --order-id ORD001
python -m pytest
```

## Project contents

- `app.py` — Streamlit prototype.
- `warehouse_optimizer.py` — data validation, feasible assignment generation,
  MIP, route policies, and route geometry.
- `data/` — order, inventory, and 101-by-101 distance matrix.
- `phase2/data/warehouse.csv` — 100-location warehouse geometry.
- `phase3/` — Phase 3 distance inputs and calculation script.
- `MATHEMATICAL_FORMULATION.md` — the MIP and routing-policy definitions.
- `docs/` — BRD, SRS, TDD, test plan/results, report, and demo guide.

## Scope and limitations

Each order requires a whole SKU quantity to be available at one location;
split picking is not supported. The MIP is optimal for the supplied shortest
network-distance matrix. The policy comparisons construct feasible aisle walks
from the layout and enumerate location choices for the sample orders. These are
project-level adapted methods, not a replication of the research paper's
network-flow/DP model or its computational results.

The data are synthetic. The warehouse distance unit is an abstract layout unit,
not a measured physical unit. See the project documents for the full assumptions
and known limitations. The app runs locally; it has not been published to a
hosting service.
