import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
src_path = root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from gasifier.coal_props import COAL_DATABASE


CASE_TO_COAL_MAP = {
    "Paper_Case_6": "ShenYou 1 (神优1)",
    "Australia_UBE": "ShenYou 2 (神优2)",
    "Fluid_Coke": "ShenYou 3 (神优3)",
    "Illinois_No6": "Illinois_No6",
    "LuNan_Texaco": "ShenYou 3 (神优3)",
    "Coal_Water_Slurry_Eastern": "ShenYou 2 (神优2)",
    "Coal_Water_Slurry_Western": "ShenYou 1 (神优1)",
    "Texaco_Exxon": "ShenYou 1 (神优1)",
    "Texaco_I-1": "ShenYou 1 (神优1)",
    "Texaco_I-2": "ShenYou 1 (神优1)",
    "Texaco_I-5C": "ShenYou 1 (神优1)",
    "Texaco_I-10": "ShenYou 1 (神优1)",
    "slurry western": "ShenYou 1 (神优1)",
    "slurry eastern": "ShenYou 2 (神优2)",
    "texaco exxon": "ShenYou 1 (神优1)",
    "texaco i-1": "ShenYou 1 (神优1)",
    "texaco i-2": "ShenYou 1 (神优1)",
    "texaco i-5c": "ShenYou 1 (神优1)",
    "texaco i-10": "ShenYou 1 (神优1)",
}


def _dulong_hhv_j_kg(C, H, O, S):
    c, h, o, s = C / 100.0, H / 100.0, O / 100.0, S / 100.0
    mj = 33.5 * c + 144.0 * h - 18.0 * o + 10.0 * s
    return mj * 1_000.0


def _coal_analysis_from_ultimate(coal_def):
    C = float(coal_def.get("C", 70.0))
    H = float(coal_def.get("H", 5.0))
    O = float(coal_def.get("O", 10.0))
    N = float(coal_def.get("N", 1.0))
    S = float(coal_def.get("S", 0.5))
    Ash = float(coal_def.get("Ash", 10.0))
    total = C + H + O + N + S + Ash
    Vd = min(40.0, max(25.0, 30.0 + max(0.0, 30.0 - (total - Ash))))
    FCd = max(0.0, 100.0 - Ash - Vd)
    return {
        "Cd": C,
        "Hd": H,
        "Od": O,
        "Nd": N,
        "Sd": S,
        "Ad": Ash,
        "Vd": Vd,
        "FCd": FCd,
        "Mt": 0.0,
        "HHV_Input": _dulong_hhv_j_kg(C, H, O, S),
    }


def _pick_coal_entry(name, case):
    coal_input = case.get("coal", {})
    if coal_input:
        return _coal_analysis_from_ultimate(coal_input)
    coal_key = case.get("coal_type") or CASE_TO_COAL_MAP.get(name)
    if coal_key and coal_key in COAL_DATABASE:
        return {
            "Cd": COAL_DATABASE[coal_key]["Cd"],
            "Hd": COAL_DATABASE[coal_key]["Hd"],
            "Od": COAL_DATABASE[coal_key]["Od"],
            "Nd": COAL_DATABASE[coal_key]["Nd"],
            "Sd": COAL_DATABASE[coal_key]["Sd"],
            "Ad": COAL_DATABASE[coal_key]["Ad"],
            "Vd": COAL_DATABASE[coal_key]["Vd"],
            "FCd": COAL_DATABASE[coal_key]["FCd"],
            "Mt": COAL_DATABASE[coal_key]["Mt"],
            "HHV_Input": COAL_DATABASE[coal_key]["HHV_d"],
        }
    return COAL_DATABASE["ShenYou 1 (神优1)"]


def _ratio_from_keys(data, keys, default=0.0):
    for key in keys:
        val = data.get(key)
        if val is not None:
            return float(val)
    return default


def _expected_gas(expected):
    result = {}
    result["TOUT_C"] = expected.get("outlet_temperature_C")
    dry = expected.get("dry_product_gas_vol_pct")
    if dry:
        for comp in ("CO", "H2", "CO2", "CH4"):
            val = dry.get(comp)
            if val is not None:
                result[f"Y_{comp}"] = val
        return result

    wet = expected.get("wet_product_gas_vol_pct")
    if wet:
        y_h2o = wet.get("H2O", expected.get("H2O", 0.0))
        ratio = 1.0 - (y_h2o / 100.0 if y_h2o is not None else 0.0)
        ratio = ratio if ratio > 0 else 1.0
        for comp in ("CO", "H2", "CO2", "CH4"):
            val = wet.get(comp)
            if val is not None:
                result[f"Y_{comp}"] = val / ratio
        return result

    for comp in ("CO", "H2", "CO2", "CH4"):
        val = expected.get(comp)
        if val is not None:
            result[f"Y_{comp}"] = float(val)
    return result


def _build_process_conditions(case, feed_type):
    cond = case.get("operating_conditions", {})
    feed_rate = cond.get("coal_feed_rate_kg_hr")
    if feed_rate is None and cond.get("coal_feed_rate_g_s"):
        feed_rate = cond["coal_feed_rate_g_s"] * 3.6
    feed_rate = float(feed_rate or 41670.0)

    oc = _ratio_from_keys(cond, ["O2_to_fuel_ratio", "O2_to_coal_ratio", "O2_to_coal_ratio_daf", "Ratio_OC"], 0.9)
    sc = _ratio_from_keys(cond, ["steam_to_fuel_ratio", "water_to_coal_ratio", "Ratio_SC"], 0.0)
    slurry = cond.get("slurry_concentration_pct")
    if slurry is None:
        slurry = 100.0 if feed_type == "Dry-fed" else 60.0
    pressure_pa = cond.get("pressure_Pa")
    if pressure_pa is None and cond.get("pressure_atm"):
        pressure_pa = cond["pressure_atm"] * 101325.0

    return {
        "FeedRate": feed_rate,
        "Ratio_OC": oc,
        "Ratio_SC": sc if feed_type != "Slurry-fed" else 0.0,
        "pt": cond.get("oxygen_purity_pct", 99.6),
        "P": float(pressure_pa or 4.08e6) / 1e6,
        "TIN": cond.get("inlet_temperature_K", 400.0),
        "HeatLossPercent": cond.get("heat_loss_percent", 2.0),
        "SlurryConc": float(slurry),
        "GasifierType": "Dry Powder" if feed_type == "Dry-fed" else "CWS",
        "HHV_Method": 0,
    }


def build_case(name, category, feed_type, case):
    coal = _pick_coal_entry(name, case)
    process = _build_process_conditions(case, feed_type)
    expected = _expected_gas(case.get("expected_results", {}))
    expected_meta = {
        "has_temperature": expected.get("TOUT_C") is not None,
        "has_composition": any(v is not None for v in (expected.get("Y_CO"), expected.get("Y_H2"), expected.get("Y_CO2"), expected.get("Y_CH4"))),
        "only_components": expected.get("TOUT_C") is None and any(v is not None for v in (expected.get("Y_CO"), expected.get("Y_H2"), expected.get("Y_CO2"), expected.get("Y_CH4")))
    }
    return {
        "Coal Analysis": coal,
        "Process Conditions": process,
        "expected_output": expected,
        "expected_meta": expected_meta,
        "case_name": f"{category}-{feed_type}-{name}",
    }


def main():
    source = Path("/Users/liuzhen/AI-projects/gasifier-1d-kinetic/data/validation_cases_final.json")
    data = json.loads(source.read_text())

    merged = {}
    for category, feeds in data.items():
        if category == "metadata":
            continue
        for feed_type, cases in feeds.items():
            for case_name, case_def in cases.items():
                key = f"{category}-{feed_type}-{case_name}"
                merged[key] = build_case(case_name, category, feed_type, case_def)

    target = root / "generated" / "validation_cases_from_kinetic.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"Generated {len(merged)} enriched cases -> {target}")


if __name__ == "__main__":
    main()
