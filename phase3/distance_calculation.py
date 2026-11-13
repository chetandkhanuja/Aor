import pandas as pd

# Load warehouse locations
warehouse = pd.read_csv("data/warehouse_locations.csv")

def calculate_distance(a, b):
    """
    Network distance between two storage locations.
    L/R sides share the same picker aisle path.
    Front cross-aisle: y=0; rear cross-aisle: y=11.
    """
    if a["aisle_id"] == b["aisle_id"]:
        return abs(a["y"] - b["y"])

    horizontal_distance = abs(a["x"] - b["x"])
    via_front = a["y"] + horizontal_distance + b["y"]
    via_rear = (11 - a["y"]) + horizontal_distance + (11 - b["y"])
    return min(via_front, via_rear)

# Calculate the full matrix, including the depot.
nodes = [{
    "location_id": "DEPOT",
    "aisle_id": "DEPOT",
    "x": 0,
    "y": 0
}] + warehouse.to_dict("records")

matrix = []
for a in nodes:
    row = {"location_id": a["location_id"]}
    for b in nodes:
        if a["location_id"] == "DEPOT" and b["location_id"] == "DEPOT":
            distance = 0
        elif a["location_id"] == "DEPOT":
            distance = b["x"] + b["y"]
        elif b["location_id"] == "DEPOT":
            distance = a["x"] + a["y"]
        else:
            distance = calculate_distance(a, b)
        row[b["location_id"]] = distance
    matrix.append(row)

distance_matrix = pd.DataFrame(matrix)
distance_matrix.to_csv("data/distance_matrix.csv", index=False)

print("Number of nodes including depot:", len(nodes))
print("Distance matrix dimensions:", distance_matrix.shape)
print("Distance matrix saved to data/distance_matrix.csv")
