"""激冷湿合成气温度平衡：与用户 Excel 表数量级对照"""

import os
import sys

import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.quench_syngas import (
    DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    DEFAULT_T_WATER_IN_CELSIUS,
    evaluate_quench_syngas,
    liquid_water_enthalpy_approx_cp,
    solve_wet_syngas_temperature_after_quench,
)


def test_trial_175c_matches_excel_magnitude():
    """Tout=175°C、42℃ 水工况：Q_release、ΔQ 与用户表一致（允许物性插值小偏差）"""
    st = evaluate_quench_syngas(
        175.0,
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        T_water_in_celsius=42.0,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    )
    assert st.T_water_in_celsius == 42.0
    assert st.H_water_in_kj_kg == liquid_water_enthalpy_approx_cp(42.0)
    assert st.evaporation_within_flow_limit is True
    # 与 Excel 手算可能差 1e-4（Cp、温差的取整）；与代码严格一致：
    assert np.isclose(st.Q_release_kj_h, 5647.0 * 2.31 * (1397.0 - 175.0), rtol=1e-9)
    assert np.isclose(st.Q_release_kj_h - st.Q_absorb_kj_h, st.delta_Q_kj_h, rtol=1e-9)
    # 用户表 ΔQ ≈ 1.007e6；插值 Psat/hg 略差时放宽
    assert 0.8e6 < st.delta_Q_kj_h < 1.2e6
    assert 0.54 < st.y_h2o < 0.57


def test_defaults_match_explicit_42c_water():
    """不传激冷水参数时使用默认温度与默认流量，与显式 42℃ 一致"""
    st_def = evaluate_quench_syngas(
        175.0,
        5647.0,
        1397.0,
        1.6013,
        2.31,
    )
    assert st_def.T_water_in_celsius == DEFAULT_T_WATER_IN_CELSIUS == 42.0
    assert st_def.cooling_water_mass_flow_kg_h == DEFAULT_COOLING_WATER_MASS_FLOW_KG_H
    st_ex = evaluate_quench_syngas(
        175.0,
        5647.0,
        1397.0,
        1.6013,
        2.31,
        T_water_in_celsius=42.0,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    )
    assert np.isclose(st_def.delta_Q_kj_h, st_ex.delta_Q_kj_h, rtol=1e-9)


def test_flow_limit_flags_insufficient_cooling_water():
    """蒸发量超过给定激冷水流量时标记为未在流量内（仅校核，不改变热平衡式）"""
    st = evaluate_quench_syngas(
        175.0,
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        T_water_in_celsius=42.0,
        cooling_water_mass_flow_kg_h=1000.0,
    )
    assert st.m_h2o_kg_h > 1000.0
    assert st.evaporation_within_flow_limit is False


def test_solve_root_small_residual():
    """求根后 ΔQ 接近 0"""
    T_out, st = solve_wet_syngas_temperature_after_quench(
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        T_water_in_celsius=42.0,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
        T_bracket_low_c=150.0,
        T_bracket_high_c=300.0,
    )
    assert abs(st.delta_Q_kj_h) < 50.0
    assert T_out > 175.0  # 在 175°C 试算时 Q_release > Q_absorb，平衡温度应更高


def test_solve_with_defaults_only():
    """仅依赖默认激冷水温度与流量仍可求解"""
    T_out, st = solve_wet_syngas_temperature_after_quench(
        5647.0,
        1397.0,
        1.6013,
        2.31,
        T_bracket_low_c=150.0,
        T_bracket_high_c=300.0,
    )
    assert abs(st.delta_Q_kj_h) < 50.0
    assert st.T_water_in_celsius == DEFAULT_T_WATER_IN_CELSIUS


def test_180c_water_inlet_bracket():
    """180℃ 饱和水：能求解且残差小"""
    T_out, st = solve_wet_syngas_temperature_after_quench(
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        T_water_in_celsius=180.0,
        water_inlet_saturated_liquid=True,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
        T_bracket_low_c=150.0,
        T_bracket_high_c=300.0,
    )
    assert abs(st.delta_Q_kj_h) < 50.0
    assert T_out > 175.0


if __name__ == "__main__":
    test_trial_175c_matches_excel_magnitude()
    test_defaults_match_explicit_42c_water()
    test_flow_limit_flags_insufficient_cooling_water()
    test_solve_root_small_residual()
    test_solve_with_defaults_only()
    test_180c_water_inlet_bracket()
    print("ok")
