"""
激冷后湿合成气平衡温度计算（干气显热 vs 蒸发吸热）

与常见 Excel 单变量求解一致：
- 假定出口温度 Tout，由饱和关系得 y_H2O = P_sat(Tout) / P_total
- 干气流量 Vdry 不变，蒸发水量使湿基水蒸气摩尔分数达到 y_H2O
- Q_release = Vdry * Cp_gas * (T_gas_in - Tout)
- Q_absorb = m_H2O * (H_vapor(Tout) - H_water_in)
- 平衡时 ΔQ = Q_release - Q_absorb = 0

物性：饱和压力与饱和汽/液焓采用分段线性插值（基于标准水蒸气表，0.1 MPa 级精度）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.optimize import brentq

# 标准态：0°C、101.325 kPa 下干基体积与摩尔换算 (与工程 Excel 常用 22.414 一致)
NM3_PER_KMOL = 22.414  # Nm³/kmol
M_H2O = 18.015  # kg/kmol

# 温度 [°C]、饱和压力 [MPa.a]、饱和液焓 [kJ/kg]、饱和汽焓 [kJ/kg]
# 数据摘自常见水蒸气表（可替换为 IAPWS 若需更高精度）
_T_C = np.array(
    [
        0,
        20,
        40,
        60,
        80,
        100,
        120,
        140,
        150,
        160,
        170,
        175,
        180,
        190,
        200,
        210,
        220,
        230,
        240,
        250,
        260,
        270,
        280,
        290,
        300,
        310,
        320,
        330,
        340,
        350,
    ],
    dtype=float,
)
_P_SAT_MPA = np.array(
    [
        0.0006117,
        0.002339,
        0.007385,
        0.019946,
        0.047414,
        0.10135,
        0.19867,
        0.36154,
        0.47616,
        0.61823,
        0.79219,
        0.8928,
        1.0028,
        1.2546,
        1.5549,
        1.9077,
        2.3198,
        2.8021,
        3.3679,
        4.0289,
        4.8026,
        5.7096,
        6.7767,
        8.0377,
        9.5377,
        11.331,
        13.49,
        16.106,
        19.286,
        16.529,
    ],
    dtype=float,
)
_HF_KJKG = np.array(
    [
        0.0,
        83.96,
        167.57,
        251.18,
        335.02,
        419.1,
        503.81,
        589.24,
        632.28,
        675.62,
        719.35,
        741.37,
        763.43,
        807.85,
        852.45,
        897.76,
        943.75,
        990.47,
        1037.7,
        1085.8,
        1134.9,
        1185.2,
        1236.9,
        1290.3,
        1345.9,
        1404.3,
        1466.1,
        1532.4,
        1604.3,
        1672.9,
    ],
    dtype=float,
)
# 干饱和蒸汽比焓 h''：随 T 升高先增后减（趋近临界点）
_HG_KJKG = np.array(
    [
        2501.6,
        2538.1,
        2574.5,
        2609.7,
        2643.8,
        2676.2,
        2706.3,
        2733.9,
        2746.6,
        2758.2,
        2768.4,
        2773.4,
        2778.1,
        2787.6,
        2796.4,
        2804.2,
        2811.2,
        2817.2,
        2822.1,
        2826.2,
        2829.7,
        2832.4,
        2834.2,
        2834.7,
        2833.1,
        2829.9,
        2824.8,
        2817.3,
        2806.7,
        2565.3,
    ],
    dtype=float,
)

assert (
    len(_T_C) == len(_P_SAT_MPA) == len(_HF_KJKG) == len(_HG_KJKG)
), "蒸汽表各列长度须一致"

# ---------------------------------------------------------------------------
# 激冷水：用户可改；默认便于直接调用/界面占位
# ---------------------------------------------------------------------------
# 典型过冷激冷水温度 [°C]（与常见 Excel 42℃ 工况一致）
DEFAULT_T_WATER_IN_CELSIUS = 42.0
# 默认激冷水质量流量 [kg/h]：取偏大值，使多数工况下蒸发量不触达上限；不需要校核时传 None
DEFAULT_COOLING_WATER_MASS_FLOW_KG_H = 80_000.0


def liquid_water_enthalpy_approx_cp(T_celsius: float, cp_kj_kg_k: float = 4.18) -> float:
    """
    过冷/液态水近似比焓（以 0°C 液相为 0 参考），与 Excel「4.18*T」一致。
    """
    return cp_kj_kg_k * float(T_celsius)


def saturation_pressure_water_mpa(T_celsius: float) -> float:
    """饱和压力 P_sat [MPa.a]，分段线性插值。"""
    T = float(T_celsius)
    return float(np.interp(T, _T_C, _P_SAT_MPA))


def saturation_enthalpy_liquid_kj_kg(T_celsius: float) -> float:
    """饱和液相比焓 h' [kJ/kg]（蒸汽表基准）。"""
    T = float(T_celsius)
    return float(np.interp(T, _T_C, _HF_KJKG))


def saturation_enthalpy_vapor_kj_kg(T_celsius: float) -> float:
    """干饱和蒸汽比焓 h'' [kJ/kg]。"""
    T = float(T_celsius)
    return float(np.interp(T, _T_C, _HG_KJKG))


def resolve_water_inlet_enthalpy_kj_kg(
    T_water_in_celsius: float,
    *,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
) -> float:
    """
    激冷水进口比焓 [kJ/kg]。

    - 若显式给出 ``H_water_in_kj_kg``，直接使用；
    - 否则：``water_inlet_saturated_liquid=True`` 时用饱和液焓 h'(T)；
      否则用过冷液近似 ``4.18 * T``（与 Excel 一致）。
    """
    if H_water_in_kj_kg is not None:
        return float(H_water_in_kj_kg)
    T = float(T_water_in_celsius)
    if water_inlet_saturated_liquid:
        return saturation_enthalpy_liquid_kj_kg(T)
    return liquid_water_enthalpy_approx_cp(T)


@dataclass
class QuenchSyngasState:
    """单次试算（给定 Tout）的中间量，单位与 Excel 列一致。"""

    T_out_c: float
    P_sat_mpa: float
    y_h2o: float
    V_h2o_nm3_h: float
    m_h2o_kg_h: float
    H_vapor_kj_kg: float
    Q_absorb_kj_h: float
    Q_release_kj_h: float
    delta_Q_kj_h: float
    T_water_in_celsius: float
    H_water_in_kj_kg: float
    cooling_water_mass_flow_kg_h: Optional[float]
    evaporation_within_flow_limit: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "T_out_C": self.T_out_c,
            "P_sat_MPa_a": self.P_sat_mpa,
            "y_H2O": self.y_h2o,
            "V_H2O_Nm3_h": self.V_h2o_nm3_h,
            "m_H2O_kg_h": self.m_h2o_kg_h,
            "H_vapor_kJ_kg": self.H_vapor_kj_kg,
            "Q_absorb_kJ_h": self.Q_absorb_kj_h,
            "Q_release_kJ_h": self.Q_release_kj_h,
            "delta_Q_kJ_h": self.delta_Q_kj_h,
            "T_water_in_C": self.T_water_in_celsius,
            "H_water_in_kJ_kg": self.H_water_in_kj_kg,
            "cooling_water_mass_flow_kg_h": self.cooling_water_mass_flow_kg_h,
            "evaporation_within_flow_limit": self.evaporation_within_flow_limit,
        }


def evaluate_quench_syngas(
    T_out_celsius: float,
    V_dry_nm3_h: float,
    T_gas_in_celsius: float,
    P_total_mpa_abs: float,
    cp_gas_kj_nm3_c: float,
    *,
    T_water_in_celsius: float = DEFAULT_T_WATER_IN_CELSIUS,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
    cooling_water_mass_flow_kg_h: Optional[float] = DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
) -> QuenchSyngasState:
    """
    给定假定出口温度 Tout，计算热量平衡残差 ΔQ = Q_release - Q_absorb。

    Parameters
    ----------
    V_dry_nm3_h : 干合成气流量 [Nm³/h]
    T_gas_in_celsius : 干气进口温度 [°C]
    P_total_mpa_abs : 系统绝压 [MPa.a]
    cp_gas_kj_nm3_c : 干合成气平均体积比热 [kJ/(Nm³·°C)]
    T_water_in_celsius : 激冷水温度 [°C]（未直接给 ``H_water_in_kj_kg`` 时参与计算进口焓）
    H_water_in_kj_kg : 激冷水进口比焓 [kJ/kg]；若给定则覆盖温度法
    water_inlet_saturated_liquid : 为 True 时用饱和液焓 h'(T_water_in)，否则用过冷液 ``4.18*T``
    cooling_water_mass_flow_kg_h : 激冷水质量流量 [kg/h]；``None`` 表示不做蒸发量与流量对比校核
    """
    T_out = float(T_out_celsius)
    P_tot = float(P_total_mpa_abs)
    if P_tot <= 0:
        raise ValueError("P_total_mpa_abs 必须为正")

    h_w_in = resolve_water_inlet_enthalpy_kj_kg(
        T_water_in_celsius,
        H_water_in_kj_kg=H_water_in_kj_kg,
        water_inlet_saturated_liquid=water_inlet_saturated_liquid,
    )

    P_sat = saturation_pressure_water_mpa(T_out)
    # 理想气体：水蒸气摩尔分数 = 分压比
    y = P_sat / P_tot
    y = float(np.clip(y, 1e-12, 0.999999))

    V_dry = float(V_dry_nm3_h)
    n_dry_kmol_h = V_dry / NM3_PER_KMOL
    n_h2o_kmol_h = n_dry_kmol_h * y / (1.0 - y)
    V_h2o = n_h2o_kmol_h * NM3_PER_KMOL
    m_h2o = n_h2o_kmol_h * M_H2O

    within_flow = True
    if cooling_water_mass_flow_kg_h is not None:
        fmax = float(cooling_water_mass_flow_kg_h)
        if fmax <= 0:
            raise ValueError("cooling_water_mass_flow_kg_h 必须为正或 None")
        within_flow = m_h2o <= fmax + 1e-6

    H_vap = saturation_enthalpy_vapor_kj_kg(T_out)
    Q_abs = m_h2o * (H_vap - h_w_in)
    Q_rel = V_dry * float(cp_gas_kj_nm3_c) * (float(T_gas_in_celsius) - T_out)

    return QuenchSyngasState(
        T_out_c=T_out,
        P_sat_mpa=P_sat,
        y_h2o=y,
        V_h2o_nm3_h=V_h2o,
        m_h2o_kg_h=m_h2o,
        H_vapor_kj_kg=H_vap,
        Q_absorb_kj_h=Q_abs,
        Q_release_kj_h=Q_rel,
        delta_Q_kj_h=Q_rel - Q_abs,
        T_water_in_celsius=float(T_water_in_celsius),
        H_water_in_kj_kg=h_w_in,
        cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
        evaporation_within_flow_limit=within_flow,
    )


def solve_wet_syngas_temperature_after_quench(
    V_dry_nm3_h: float,
    T_gas_in_celsius: float,
    P_total_mpa_abs: float,
    cp_gas_kj_nm3_c: float,
    *,
    T_water_in_celsius: float = DEFAULT_T_WATER_IN_CELSIUS,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
    cooling_water_mass_flow_kg_h: Optional[float] = DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    T_bracket_low_c: float = 50.0,
    T_bracket_high_c: Optional[float] = None,
    xtol: float = 1e-4,
) -> Tuple[float, QuenchSyngasState]:
    """
    求使 ΔQ=0 的出口平衡温度 [°C]，并返回该温度下的完整状态。

    在 [T_bracket_low_c, T_bracket_high_c] 内用 brentq 求根；
    默认上界为 min(T_gas_in - 0.5, 349) °C（须低于临界区插值上限）。
    """
    T_hi = T_bracket_high_c
    if T_hi is None:
        T_hi = min(float(T_gas_in_celsius) - 0.5, 349.0)
    T_lo = float(T_bracket_low_c)
    if T_lo >= T_hi:
        raise ValueError("温度搜索区间无效：T_bracket_low_c 须小于上界")

    def residual(T: float) -> float:
        st = evaluate_quench_syngas(
            T,
            V_dry_nm3_h,
            T_gas_in_celsius,
            P_total_mpa_abs,
            cp_gas_kj_nm3_c,
            T_water_in_celsius=T_water_in_celsius,
            H_water_in_kj_kg=H_water_in_kj_kg,
            water_inlet_saturated_liquid=water_inlet_saturated_liquid,
            cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
        )
        return st.delta_Q_kj_h

    f_lo = residual(T_lo)
    f_hi = residual(T_hi)
    if f_lo * f_hi > 0:
        raise ValueError(
            f"在给定区间 [{T_lo}, {T_hi}] °C 内未找到变号，无法保证存在根。"
            f" f({T_lo})={f_lo:.4g}, f({T_hi})={f_hi:.4g}。"
            "请检查输入或扩大/移动搜索区间。"
        )

    T_root = brentq(residual, T_lo, T_hi, xtol=xtol, rtol=1e-8)
    final = evaluate_quench_syngas(
        T_root,
        V_dry_nm3_h,
        T_gas_in_celsius,
        P_total_mpa_abs,
        cp_gas_kj_nm3_c,
        T_water_in_celsius=T_water_in_celsius,
        H_water_in_kj_kg=H_water_in_kj_kg,
        water_inlet_saturated_liquid=water_inlet_saturated_liquid,
        cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
    )
    return float(T_root), final


def example_cases_documentation() -> Dict[str, Any]:
    """文档用：与用户表相同的两组已知量及试算 Tout=175°C 的预期数量级。"""
    base = dict(
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    )
    case_42 = dict(
        name="42℃ 水（过冷液，H≈4.18*T）",
        T_water_in_celsius=42.0,
        **base,
    )
    case_180 = dict(
        name="180℃ 水（饱和液，宜用蒸汽表 h'）",
        T_water_in_celsius=180.0,
        water_inlet_saturated_liquid=True,
        **base,
    )
    T_try = 175.0
    out: Dict[str, Any] = {}
    for key, inp in [("case_42C", case_42), ("case_180C", case_180)]:
        params = {k: v for k, v in inp.items() if k != "name"}
        st = evaluate_quench_syngas(T_try, **params)
        out[key] = {"inputs": inp, "trial_T_out_175C": st.to_dict()}
    return out
