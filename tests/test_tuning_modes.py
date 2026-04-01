import json
import os
import sys


current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from scripts.audit_validation_cases import build_inputs
from scripts.validation_profile import maybe_search_char_extent


def _load_case(case_name):
    path = os.path.join(project_root, "generated", "validation_cases_from_kinetic.json")
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    case = cases[case_name]
    inputs = case["Coal Analysis"].copy()
    inputs.update(case["Process Conditions"])
    inputs.setdefault("TIN", 300.0)
    inputs.setdefault("TR", 1400.0)
    inputs.setdefault("HHV_Method", 0)
    return inputs


def test_grouped_default_carbon_conversion_for_industrial_cws():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["CarbonConversionMode"] = "grouped_default_v1"
    model = GasifierModel(inputs)
    model._preprocess_inputs()
    assert model.inputs["CarbonConversion"] == 0.99


def test_effective_split_v2_preserves_physical_less_than_pilot_for_industrial():
    industrial_inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    industrial_inputs["HeatLossMode"] = "effective_split_v2"
    industrial_model = GasifierModel(industrial_inputs)
    industrial_model._preprocess_inputs()

    pilot_inputs = _load_case("Pilot-Slurry-fed-Coal_Water_Slurry_Eastern")
    pilot_inputs["HeatLossMode"] = "effective_split_v2"
    pilot_model = GasifierModel(pilot_inputs)
    pilot_model._preprocess_inputs()

    assert industrial_model.inputs["PhysicalHeatLossPercent"] < pilot_model.inputs["PhysicalHeatLossPercent"]
    assert industrial_model.inputs["HeatLossPercent"] == (
        industrial_model.inputs["PhysicalHeatLossPercent"]
        + industrial_model.inputs["ModelCorrectionPercent"]
    )
    assert industrial_model.inputs["ModelCorrectionPercent"] == 9.0


def test_grouped_delta_t_mode_uses_zero_wgs_for_industrial_cws():
    industrial_inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    industrial_inputs["DeltaTMode"] = "grouped_default_v2"
    industrial_model = GasifierModel(industrial_inputs)
    industrial_model._preprocess_inputs()

    pilot_inputs = _load_case("Pilot-Slurry-fed-Coal_Water_Slurry_Eastern")
    pilot_inputs["DeltaTMode"] = "grouped_default_v2"
    pilot_model = GasifierModel(pilot_inputs)
    pilot_model._preprocess_inputs()

    assert industrial_model.inputs["DeltaT_WGS"] == 0.0
    assert pilot_model.inputs["DeltaT_WGS"] == 150.0


def test_grouped_delta_t_mode_uses_meth_shift_for_low_h_industrial_cws():
    inputs = _load_case("Industrial-Slurry-fed-Fluid_Coke")
    inputs["DeltaTMode"] = "grouped_default_v2"
    model = GasifierModel(inputs)
    model._preprocess_inputs()

    assert model.inputs["DeltaT_WGS"] == 0.0
    assert model.inputs["DeltaT_Meth"] == 0.0


def test_calibrated_split_heat_loss_updates_correction_only():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["HeatLossMode"] = "effective_split_v2"
    model = GasifierModel(inputs)
    model._preprocess_inputs()
    original_physical = model.inputs["PhysicalHeatLossPercent"]

    model._apply_total_heat_loss_percent(8.0)
    model.inputs["HeatLossMode"] = "manual_split"
    model._preprocess_inputs()

    assert model.inputs["PhysicalHeatLossPercent"] == original_physical
    assert model.inputs["ModelCorrectionPercent"] == 8.0 - original_physical
    assert model.inputs["HeatLossPercent"] == 8.0


def test_negative_total_effective_loss_is_allowed_in_split_mode():
    inputs = _load_case("Pilot-Dry-fed-Texaco_I-2")
    inputs["HeatLossMode"] = "effective_split_v2"
    model = GasifierModel(inputs)
    model._preprocess_inputs()

    physical = model.inputs["PhysicalHeatLossPercent"]
    model.inputs["HeatLossMode"] = "manual_split"
    model._apply_total_heat_loss_percent(-1.5)
    model._preprocess_inputs()

    assert model.inputs["PhysicalHeatLossPercent"] == physical
    assert model.inputs["ModelCorrectionPercent"] == -1.5 - physical
    assert model.inputs["HeatLossPercent"] == -1.5


def test_explicit_char_extent_mode_exposes_residual_carbon():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["SolverMethod"] = "Stoic"
    inputs["HeatLossMode"] = "effective_split_v2"
    inputs["CarbonConversionMode"] = "grouped_default_v1"
    inputs["DeltaTMode"] = "grouped_default_v2"
    inputs["CharExtentMode"] = "explicit_v1"
    model = GasifierModel(inputs)
    result = model.run_simulation()

    assert result["CharExtent"] is not None
    assert 0.0 <= result["CharExtent"] <= 1.0
    assert result["ResidualCarbonMol"] >= 0.0
    assert result["GasCarbonFraction"] <= 1.0


def test_correlation_char_extent_mode_updates_with_temperature():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["SolverMethod"] = "Stoic"
    inputs["HeatLossMode"] = "effective_split_v2"
    inputs["CarbonConversionMode"] = "grouped_default_v1"
    inputs["DeltaTMode"] = "grouped_default_v2"
    inputs["CharExtentMode"] = "correlation_v2"
    model = GasifierModel(inputs)
    model._preprocess_inputs()

    low_extent = model._estimate_char_extent_from_correlation(1200.0 + 273.15)
    high_extent = model._estimate_char_extent_from_correlation(1500.0 + 273.15)

    assert 0.94 <= low_extent <= 0.999
    assert 0.94 <= high_extent <= 0.999
    assert high_extent >= low_extent


def test_self_consistent_delta_t_updates_effective_values():
    inputs = _load_case("Pilot-Slurry-fed-Coal_Water_Slurry_Eastern")
    inputs["SolverMethod"] = "Stoic"
    inputs["DeltaTMode"] = "grouped_self_consistent_v3"
    inputs["DeltaT_WGS"] = 150.0
    inputs["DeltaT_Meth"] = 0.0
    model = GasifierModel(inputs)
    result = model.run_simulation()

    assert result["diagnostics"]["total_warnings"] == 0
    assert result["DeltaT_WGS_Effective"] is not None
    assert result["DeltaT_WGS_Effective"] != 150.0


def test_extended_char_reaction_set_runs():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["SolverMethod"] = "Stoic"
    inputs["HeatLossMode"] = "effective_split_v2"
    inputs["CarbonConversionMode"] = "grouped_default_v1"
    inputs["DeltaTMode"] = "grouped_default_v2"
    inputs["StoicReactionSet"] = "extended_char_v1"
    model = GasifierModel(inputs)
    result = model.run_simulation()

    assert result["TOUT_C"] > 500.0
    assert result["diagnostics"]["total_warnings"] >= 0


def test_char_submodel_reaction_set_runs():
    inputs = _load_case("Industrial-Slurry-fed-Illinois_No6")
    inputs["SolverMethod"] = "Stoic"
    inputs["HeatLossMode"] = "effective_split_v2"
    inputs["CarbonConversionMode"] = "grouped_default_v1"
    inputs["DeltaTMode"] = "grouped_default_v2"
    inputs["StoicReactionSet"] = "char_submodel_v2"
    model = GasifierModel(inputs)
    result = model.run_simulation()

    assert result["TOUT_C"] > 500.0


def test_char_extent_search_helper_returns_supported_candidate():
    class Args:
        profile = "tuned-19cases"
        solver_method = None
        carbon_conversion = None
        delta_t_wgs = None
        delta_t_meth = None

    path = os.path.join(project_root, "generated", "validation_cases_from_kinetic.json")
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)

    case = cases["Industrial-Slurry-fed-Illinois_No6"]
    inputs = build_inputs(case, Args)
    result = maybe_search_char_extent(GasifierModel(dict(inputs)), case["expected_output"])

    assert result is not None
    assert result[5] in {0.94, 0.96, 0.98, 0.99, 0.999}
