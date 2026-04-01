import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from gasifier.gasifier import GasifierModel


TUNED_19CASES_PROFILE = {
    "SolverMethod": "Stoic",
    "HeatLossMode": "effective_split_v2",
    "CarbonConversionMode": "grouped_default_v1",
    "DeltaTMode": "grouped_default_v2",
    "CharExtentMode": "correlation_v2",
}

CANDIDATE_CHAR_EXTENTS = (0.94, 0.96, 0.98, 0.99, 0.999)


def build_profile_inputs(case, profile=None):
    inputs = case["Coal Analysis"].copy()
    inputs.update(case["Process Conditions"])
    inputs.setdefault("TIN", 300.0)
    inputs.setdefault("TR", 1400.0)
    inputs.setdefault("HHV_Method", 0)
    if profile == "tuned-19cases":
        inputs.update(TUNED_19CASES_PROFILE)
    return inputs


def calc_errors(results, expected):
    errors = {}
    if expected.get("TOUT_C") is not None:
        errors["T_error_C"] = results["TOUT_C"] - expected["TOUT_C"]
    for exp_key, pred_key in {
        "Y_CO": "Y_CO_dry",
        "Y_H2": "Y_H2_dry",
        "Y_CO2": "Y_CO2_dry",
        "Y_CH4": "Y_CH4_dry",
    }.items():
        if expected.get(exp_key) is not None:
            errors[f"{exp_key}_error"] = results[pred_key] - expected[exp_key]
    return errors


def composite_score(errors):
    comp_terms = [
        abs(errors[k]) for k in ("Y_CO_error", "Y_H2_error", "Y_CO2_error") if k in errors
    ]
    comp_mae = sum(comp_terms) / len(comp_terms) if comp_terms else 0.0
    temp_abs = abs(errors.get("T_error_C", 0.0)) if "T_error_C" in errors else 0.0
    return comp_mae + temp_abs / 50.0


def maybe_calibrate_heat_loss(model, expected):
    target_t = expected.get("TOUT_C")
    if target_t is None:
        return {"calibrated_ratio_oc": None, "calibrated_heat_loss_percent": None}
    loss_pct, _ = model.calculate_heat_loss_for_target_T(target_t + 273.15)
    if loss_pct is None:
        return {"calibrated_ratio_oc": None, "calibrated_heat_loss_percent": None}
    total_loss_pct = loss_pct
    if "PhysicalHeatLossPercent" in model.inputs or model.inputs.get("HeatLossMode") == "effective_split_v2":
        model.inputs["HeatLossMode"] = "manual_split"
    else:
        total_loss_pct = max(0.0, total_loss_pct)
        model.inputs["HeatLossMode"] = "manual"
    model._apply_total_heat_loss_percent(total_loss_pct)
    model._preprocess_inputs()
    return {
        "calibrated_ratio_oc": None,
        "calibrated_heat_loss_percent": model.inputs["HeatLossPercent"],
    }


def maybe_calibrate_oc_then_heat_loss(model, expected):
    target_t = expected.get("TOUT_C")
    if target_t is None:
        return {"calibrated_ratio_oc": None, "calibrated_heat_loss_percent": None}

    target_t_k = target_t + 273.15
    calibrated_ratio_oc = None
    if "PhysicalHeatLossPercent" in model.inputs or model.inputs.get("HeatLossMode") == "effective_split_v2":
        model._preprocess_inputs()
        physical_loss_pct = float(model.inputs.get("PhysicalHeatLossPercent", 0.0))
        try:
            calibrated_ratio_oc = model.calculate_oxygen_ratio_for_target_T(
                target_t_k, fixed_loss_percent=physical_loss_pct
            )
            model.inputs["Ratio_OC"] = calibrated_ratio_oc
            model.inputs["HeatLossMode"] = "manual_split"
            model._apply_total_heat_loss_percent(physical_loss_pct)
            model._preprocess_inputs()
        except ValueError:
            calibrated_ratio_oc = None

    loss_pct, _ = model.calculate_heat_loss_for_target_T(target_t_k)
    if loss_pct is None:
        return {
            "calibrated_ratio_oc": calibrated_ratio_oc,
            "calibrated_heat_loss_percent": None,
        }
    total_loss_pct = loss_pct
    if "PhysicalHeatLossPercent" in model.inputs or model.inputs.get("HeatLossMode") == "effective_split_v2":
        model.inputs["HeatLossMode"] = "manual_split"
    else:
        total_loss_pct = max(0.0, total_loss_pct)
        model.inputs["HeatLossMode"] = "manual"
    model._apply_total_heat_loss_percent(total_loss_pct)
    model._preprocess_inputs()
    return {
        "calibrated_ratio_oc": calibrated_ratio_oc,
        "calibrated_heat_loss_percent": model.inputs["HeatLossPercent"],
    }


def maybe_search_char_extent(model, expected):
    best = None
    for char_extent in CANDIDATE_CHAR_EXTENTS:
        trial = GasifierModel(dict(model.inputs))
        trial.inputs["CharExtentMode"] = "explicit_v1"
        trial.inputs["CarbonConversionMode"] = "manual"
        trial.inputs["CarbonConversion"] = char_extent
        calibration = {"calibrated_ratio_oc": None, "calibrated_heat_loss_percent": None}
        if expected.get("TOUT_C") is not None:
            calibration = maybe_calibrate_heat_loss(trial, expected)
        trial_results = trial.run_simulation()
        trial_errors = calc_errors(trial_results, expected)
        record = (
            composite_score(trial_errors),
            trial,
            calibration,
            trial_results,
            trial_errors,
            char_extent,
        )
        if best is None or record[0] < best[0]:
            best = record
    return best


def select_best_validation_candidate(inputs, expected, calibrate_heat_loss=True):
    candidates = []

    model = GasifierModel(dict(inputs))
    calibration = {"calibrated_ratio_oc": None, "calibrated_heat_loss_percent": None}
    if calibrate_heat_loss:
        calibration = maybe_calibrate_heat_loss(model, expected)
    results = model.run_simulation()
    errors = calc_errors(results, expected)
    candidates.append(("heat_loss_only", model, calibration, results, errors))

    if calibrate_heat_loss and expected.get("TOUT_C") is not None:
        model_oc = GasifierModel(dict(inputs))
        calibration_oc = maybe_calibrate_oc_then_heat_loss(model_oc, expected)
        results_oc = model_oc.run_simulation()
        errors_oc = calc_errors(results_oc, expected)
        candidates.append(("oc_first_then_heat_loss", model_oc, calibration_oc, results_oc, errors_oc))

    if inputs.get("CharExtentMode") in {"explicit_v1", "correlation_v2"}:
        searched = maybe_search_char_extent(GasifierModel(dict(inputs)), expected)
        if searched is not None:
            _, model_char, calibration_char, results_char, errors_char, searched_extent = searched
            candidates.append(
                (
                    f"char_extent_search_{searched_extent}",
                    model_char,
                    calibration_char,
                    results_char,
                    errors_char,
                )
            )

    return min(candidates, key=lambda item: composite_score(item[4]))
