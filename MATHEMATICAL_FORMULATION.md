# Phase 4 — Mathematical Formulation

## Scope

For one customer order, choose one stocked location for each SKU and a closed
depot-to-depot picking tour. The MIP uses shortest-path distances from the Phase
3 matrix. It is an adapted location-selection/TSP benchmark for this prototype,
not a reproduction of the paper's dynamic-programming/network-flow model.

## Sets and parameters

- \(S\): SKUs in the selected order.
- \(L_s\): locations containing SKU \(s\) with enough stock for its complete demand.
- \(N = \bigcup_{s\in S} L_s\): candidate picking locations.
- \(V = \{\text{DEPOT}\}\cup N\).
- \(q_s\): order demand for SKU \(s\).
- \(a_{sl}\): available quantity of SKU \(s\) at location \(l\).
- \(d_{ij}\): shortest feasible warehouse-network distance from \(i\) to \(j\).

## Decision variables

- \(x_{sl}\in\{0,1\}\): SKU \(s\) is assigned to location \(l\).
- \(z_l\in\{0,1\}\): the picker visits location \(l\).
- \(y_{ij}\in\{0,1\}\): the route uses arc \(i\rightarrow j\).
- \(u_l\): MTZ visit-order variable for candidate location \(l\).

## Objective

\[
\min \sum_{i\in V}\sum_{\substack{j\in V\\j\ne i}} d_{ij}y_{ij}
\]

## Constraints

**Fulfil each SKU from one eligible location**
\[
\sum_{l\in L_s}x_{sl}=1 \qquad \forall s\in S.
\]
Locations where \(a_{sl}<q_s\) are omitted from \(L_s\); split picking is not
supported.

**Link assignments and visits**
\[
x_{sl}\le z_l \quad \forall s,l;\qquad
z_l\le \sum_{s:l\in L_s}x_{sl}\quad \forall l\in N.
\]
This OR-link also supports more than one SKU being assigned to a physical
location.

**Route degree**
\[
\sum_{j\in V,j\ne l}y_{lj}=z_l,\quad
\sum_{j\in V,j\ne l}y_{jl}=z_l \qquad \forall l\in N.
\]
\[
\sum_{j\in N}y_{\text{DEPOT},j}=1,\qquad
\sum_{i\in N}y_{i,\text{DEPOT}}=1.
\]

**Subtour elimination (MTZ)**
\[
u_i-u_j+M y_{ij}\le M-1\quad \forall i\ne j,\ i,j\in N,
\qquad z_i\le u_i\le Mz_i,
\]
where \(M=|N|\).

The binary variables are \(x,z,y\). The MIP benchmark is solved with Pyomo and
HiGHS; a solution is reported as optimal only when HiGHS returns an optimal
termination condition.

## Routing policies used for comparison

The three constructive comparisons are policy-constrained warehouse walks,
not additional MIP constraints:

- **Return:** service each selected aisle from the front cross-aisle and return
  to the front before moving to the next aisle.
- **Traversal:** process selected aisles in aisle order, traversing each aisle
  from end to end and alternating the direction. If the route ends at the rear,
  it returns through the nearest aisle line.
- **Largest Gap:** in each aisle, find the longest interval between pick
  positions (including the aisle ends), service picks from the front and rear
  sides of that gap, and connect the two cross-aisle sweeps through a selected
  aisle line. The connecting pass can cross the gap in that one bridge aisle.

For each heuristic, the implementation enumerates the feasible location
assignments in the sample data and keeps the lowest-distance route for that
policy. The exact MIP instead jointly optimizes assignment and route using the
distance matrix.

## Assumptions and limitations

- Five parallel aisles, ten positions per aisle side, front cross-aisle at
  \(y=0\), rear cross-aisle at \(y=11\), depot at \((0,0)\).
- Left/right rack faces at a position share the same picker-aisle path.
- One picker and one order are planned at a time; no congestion, replenishment,
  service time, pick precedence, capacity, or multiple-picker interactions.
- The data are synthetic and are not the experimental data from the paper.
- MIP distances are the supplied network-distance matrix; the policy walks are
  generated on the warehouse layout. This is a project benchmark and should not
  be presented as a reproduction of the paper's exact formulation or results.
