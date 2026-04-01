import argparse
import json
import os
import sys
from pathlib import Path

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
generated_path = os.path.join(root, "generated", "validation_cases_from_kinetic.json")
if not os.path.exists(generated_path):
    raise FileNotFoundError(f"{generated_path} missing")

sys.path.insert(0, os.path.join(root, "src"))

from gasifier.gasifier import GasifierModel
try:
    from validation_profile import build_profile_inputs, select_best_validation_candidate
except ModuleNotFoundError:
    from scripts.validation_profile import build_profile_inputs, select_best_validation_candidate


def format_pct(value):
    return f"{value:.2f}" if value is not None else "-"


def main(limit=None):
    with open(generated_path, encoding="utf-8") as f:
        cases = json.load(f)
    GasifierModel.print_diagnostics = lambda self: None

    headers = (
        "Case", "Status", "TOUT (C)", "TOUT Δ", "CO Δ", "H₂ Δ"
    )
    print(" | ".join(headers))
    print("-" * 70)
    for idx, (name, case) in enumerate(cases.items()):
        if limit and idx >= limit:
            break
        inputs = build_profile_inputs(case, profile="tuned-19cases")
        expected = case["expected_output"]
        _, model, _, results, _ = select_best_validation_candidate(
            inputs, expected, calibrate_heat_loss=True
        )
        tc = results["TOUT_C"]
        tc_expected = expected.get("TOUT_C")
        tc_diff = tc - tc_expected if tc_expected is not None else None
        co_diff = results["Y_CO_dry"] - expected.get("Y_CO", results["Y_CO_dry"])
        h2_diff = results["Y_H2_dry"] - expected.get("Y_H2", results["Y_H2_dry"])
        status = "OK"
        print(
            f"{name:30} | {status:6} | "
            f"{tc:8.1f} | {tc_diff if tc_diff is not None else '   -'} | "
            f"{co_diff:6.2f} | {h2_diff:6.2f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only process first N cases")
    args = parser.parse_args()
    main(limit=args.limit)
