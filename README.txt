WAREHOUSE OPTIMIZATION PROJECT — UPDATED PHASE 2 DATA

Warehouse layout:
- 5 parallel picker aisles (A1-A5)
- 10 storage positions on each side (L and R) of each aisle
- 100 total storage locations (5 x 10 x 2)
- Aisle x-coordinates: A1=2, A2=6, A3=10, A4=14, A5=18
- Position y-coordinates: 1 through 10
- Front cross-aisle: y=0
- Rear cross-aisle: y=11
- Depot: (0,0)

Location notation:
- A3-L7 means aisle A3, left rack face, position 7.
- A3-R7 means aisle A3, right rack face, position 7.
- L/R distinguish inventory locations, but picking either side uses the same aisle travel path.
- The two rack faces at the same aisle and position have the same travel distance from the aisle path.

Files:
- warehouse.csv: all 100 storage locations
- inventory.csv: 10 SKUs, each available at two storage locations
- orders.csv: two sample customer orders

Important modeling note:
The side label distinguishes storage locations and inventory, not separate travel lanes.
The picker walks along the aisle and can pick from either side without changing aisles.
For now, x and y are abstract travel coordinates. The aisle/cross-aisle network distance rules
will be documented and validated in the next step.

This is synthetic project data, not the original research paper's experimental dataset.
