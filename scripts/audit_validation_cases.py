import argparse
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gasifier.gasifier import GasifierModel
try:
    from validation_profile import (
        build_profile_inputs,
        select_best_validation_candidate,
    )
except ModuleNotFoundError:
    from scripts.validation_profile import (
        build_profile_inputs,
        select_best_validation_candidate,
    )


def build_inputs(case, args):
    inputs = build_profile_inputs(case, profile=args.profile)
    if args.solver_method:
        inputs["SolverMethod"] = args.solver_method
    if args.carbon_conversion is not None:
        inputs["CarbonConversion"] = args.carbon_conversion
    if args.delta_t_wgs is not None:
        inputs["DeltaT_WGS"] = args.delta_t_wgs
    if args.delta_t_meth is not None:
        inputs["DeltaT_Meth"] = args.delta_t_meth
    return inputs


def score_case(errors, diagnostics):
    comp_terms = [
        abs(errors[k]) for k in ("Y_CO_error", "Y_H2_error", "Y_CO2_error") if k in errors
    ]
    return {
        "temp_abs": abs(errors.get("T_error_C", 0.0)) if "T_error_C" in errors else None,
        "comp_mae": sum(comp_terms) / len(comp_terms) if comp_terms else None,
        "warnings": diagnostics["total_warnings"],
        "candidate_failures": len(diagnostics["details"].get("candidate_failures", [])),
        "mass_issues": diagnostics["mass_balance_issues"],
        "constraints": diagnostics["constraint_violations"],
    }


def aggregate(records):
    temp = [r["score"]["temp_abs"] for r in records if r["score"]["temp_abs"] is not None]
    comp = [r["score"]["comp_mae"] for r in records if r["score"]["comp_mae"] is not None]
    warnings_total = [r["score"]["warnings"] for r in records]
    candidate_failures = [r["score"]["candidate_failures"] for r in records]
    return {
        "case_count": len(records),
        "avg_temp_abs_error_C": sum(temp) / len(temp) if temp else None,
        "avg_comp_mae": sum(comp) / len(comp) if comp else None,
        "avg_final_warnings": sum(warnings_total) / len(warnings_total) if warnings_total else 0.0,
        "avg_candidate_failures": sum(candidate_failures) / len(candidate_failures) if candidate_failures else 0.0,
        "max_final_warnings": max(warnings_total) if warnings_total else 0,
        "cases_with_final_warnings": sum(1 for x in warnings_total if x > 0),
        "top_problem_cases": [
            {
                "case": r["case"],
                "temp_abs": r["score"]["temp_abs"],
                "comp_mae": r["score"]["comp_mae"],
                "warnings": r["score"]["warnings"],
            }
            for r in sorted(
                records,
                key=lambda r: (
                    r["score"]["warnings"],
                    r["score"]["comp_mae"] or 0.0,
                    r["score"]["temp_abs"] or 0.0,
                ),
                reverse=True,
            )[:8]
        ],
        "gasifier_type_counts": dict(Counter(r["gasifier_type"] for r in records)),
    }


def main():
    parser = argparse.ArgumentParser(description="Audit all 19 validation cases.")
    parser.add_argument("--profile", choices=["tuned-19cases"], default=None)
    parser.add_argument("--solver-method", choices=["RGibbs", "Stoic"], default=None)
    parser.add_argument("--carbon-conversion", type=float, default=None)
    parser.add_argument("--delta-t-wgs", type=float, default=None)
    parser.add_argument("--delta-t-meth", type=float, default=None)
    parser.add_argument("--calibrate-heat-loss", action="store_true")
    parser.add_argument(
        "--cases-path",
        default=str(ROOT / "generated" / "validation_cases_from_kinetic.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "generated" / "validation" / "validation_audit.json"),
    )
    args = parser.parse_args()

    cases = json.loads(Path(args.cases_path).read_text(encoding="utf-8"))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    GasifierModel.print_diagnostics = lambda self: None
    calibrate_heat_loss = args.calibrate_heat_loss or args.profile == "tuned-19cases"

    records = []
    for name, case in cases.items():
        inputs = build_inputs(case, args)
        expected = case["expected_output"]
        calibration_strategy, model, calibration, results, errors = select_best_validation_candidate(
            inputs, expected, calibrate_heat_loss=calibrate_heat_loss
        )
        records.append(
            {
                "case": name,
                "calibration_strategy": calibration_strategy,
                "gasifier_type": inputs.get("GasifierType", ""),
                "carbon_conversion": inputs.get("CarbonConversion"),
                "char_extent_mode": inputs.get("CharExtentMode"),
                "char_extent_used": results.get("CharExtent"),
                "residual_carbon_mol": results.get("ResidualCarbonMol"),
                "ratio_oc_input": case["Process Conditions"].get("Ratio_OC"),
                "ratio_oc_used": model.inputs.get("Ratio_OC"),
                "effective_heat_loss_percent": model.inputs.get("HeatLossPercent"),
                "physical_heat_loss_percent": model.inputs.get("PhysicalHeatLossPercent"),
                "model_correction_percent": model.inputs.get("ModelCorrectionPercent"),
                "calibrated_ratio_oc": calibration["calibrated_ratio_oc"],
                "calibrated_heat_loss_percent": calibration["calibrated_heat_loss_percent"],
                "expected": expected,
                "predicted": {
                    "TOUT_C": results["TOUT_C"],
                    "Y_CO": results["Y_CO_dry"],
                    "Y_H2": results["Y_H2_dry"],
                    "Y_CO2": results["Y_CO2_dry"],
                    "Y_CH4": results["Y_CH4_dry"],
                },
                "errors": errors,
                "diagnostics": results["diagnostics"],
                "score": score_case(errors, results["diagnostics"]),
            }
        )

    payload = {
        "config": {
            "profile": args.profile,
            "solver_method": args.solver_method,
            "carbon_conversion": args.carbon_conversion,
            "delta_t_wgs": args.delta_t_wgs,
            "delta_t_meth": args.delta_t_meth,
            "char_extent_mode": "correlation_v2" if args.profile == "tuned-19cases" else None,
            "calibrate_heat_loss": calibrate_heat_loss,
        },
        "summary": aggregate(records),
        "records": records,
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = payload["summary"]
    print(f"cases={summary['case_count']}")
    print(f"avg_temp_abs_error_C={summary['avg_temp_abs_error_C']}")
    print(f"avg_comp_mae={summary['avg_comp_mae']}")
    print(f"avg_final_warnings={summary['avg_final_warnings']}")
    print(f"avg_candidate_failures={summary['avg_candidate_failures']}")
    print(f"max_final_warnings={summary['max_final_warnings']}")
    print(f"cases_with_final_warnings={summary['cases_with_final_warnings']}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
