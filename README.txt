PHASE 3 — DISTANCE CALCULATION

Assumptions:
- 5 picker aisles, A1-A5, with x-coordinates 2, 6, 10, 14, 18.
- Positions have y-coordinates 1 through 10.
- Front cross-aisle y=0; rear cross-aisle y=11.
- Depot is at (0,0), with access to the front cross-aisle.
- Left and right rack faces share the same picker aisle path.
- Movement between different aisles is via the front or rear cross-aisle.
- No direct lateral connection between aisles is assumed at intermediate y positions.

Formulas:
Same aisle: abs(y_i-y_j)
Different aisles:
  via_front = y_i + abs(x_i-x_j) + y_j
  via_rear = (11-y_i) + abs(x_i-x_j) + (11-y_j)
  distance = min(via_front, via_rear)
Depot to location: x_i + y_i

Files:
- data/warehouse_locations.csv: 100 storage locations
- data/distance_matrix.csv: 101 x 101 matrix including depot
- data/depot_distances.csv: distance from depot to each storage location
- distance_calculation.py: reproducible Python script

Distances are abstract units, not metres.
