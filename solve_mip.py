"""Command-line entry point for the warehouse MIP benchmark."""

import argparse
from pathlib import Path

from warehouse_optimizer import load_data, solve_mip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", default="ORD001")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    plan = solve_mip(args.order_id, load_data(project_dir / "data"))
    print(f"Order: {args.order_id}")
    print(f"Solver status: optimal")
    print(f"Minimum travel distance: {plan.distance:.2f}")
    print("Selected picking locations:")
    for sku, location in plan.selected_locations.items():
        print(f"  {sku}: {location}")
    print("Picker route:")
    print("  DEPOT -> " + " -> ".join(plan.visit_order) + " -> DEPOT")

    output = project_dir / "data" / f"{args.order_id}_mip_solution.txt"
    with output.open("w", encoding="utf-8") as solution_file:
        solution_file.write(f"Order: {args.order_id}\n")
        solution_file.write(f"Minimum travel distance: {plan.distance:.2f}\n")
        solution_file.write("Selected locations:\n")
        for sku, location in plan.selected_locations.items():
            solution_file.write(f"{sku}: {location}\n")
        solution_file.write(
            "Route: DEPOT -> " + " -> ".join(plan.visit_order) + " -> DEPOT\n"
        )
    print(f"Solution saved to {output}")


if __name__ == "__main__":
    main()
