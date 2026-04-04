"""
gasifier_ui.py - Streamlit Web UI for Gasifier Model (Chem Portal Integration)

================================================================================
MODIFICATION HISTORY
================================================================================
2026-01-28  v2.0  刘臻 (Liu Zhen)
    - [Refactor] 从 app.py 重命名为 gasifier_ui.py，用于 Chem Portal 集成
    - [Layout] Line 47-49: 从 Sidebar 布局改为双列布局 (col_input, col_result)
    - [API] Line 35-38: 封装 run() 函数以支持外部模块调用
    - [Feature] Line 126-150: 智能校正功能 (热损/氧煤比自动调整)
    - [Feature] Line 210-215: 诊断信息展示 (能量/元素平衡)
    - [UI] Line 171-204: 优化结果展示 (KPI卡片 + 饼图)
2026-03-24  v2.1  刘臻
    - [Feature] Tabs 增加「激冷湿合成气」计算器，集成 quench_syngas.py
    - [Fix] 验证工况对比条件与下拉框一致；气化炉 input_data 排除 quench_* 键
================================================================================
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Add src to path so we can import gasifier package
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)
scripts_path = os.path.join(current_dir, 'scripts')
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from gasifier.gasifier import GasifierModel
from gasifier.coal_props import COAL_DATABASE
from gasifier.validation_case_bundle import load_validation_case_bundle
from gasifier.quench_syngas import (
    DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    DEFAULT_T_WATER_IN_CELSIUS,
    evaluate_quench_syngas,
    solve_wet_syngas_temperature_after_quench,
)
from validation_profile import (
    TUNED_19CASES_PROFILE,
    build_calibration_config,
    build_profile_inputs,
    select_best_validation_candidate,
)


PROJECT_ROOT = Path(current_dir)
GENERATED_CASES_PATH = PROJECT_ROOT / "generated" / "validation_cases_from_kinetic.json"
VALIDATION_RESULT_PATHS = (
    PROJECT_ROOT / "generated" / "validation" / "validation_results.json",
    PROJECT_ROOT / "tests" / "validation_results.json",
)


def _load_generated_cases():
    if GENERATED_CASES_PATH.exists():
        return json.loads(GENERATED_CASES_PATH.read_text(encoding="utf-8"))
    return load_validation_case_bundle()


def _load_validation_snapshot():
    for path in VALIDATION_RESULT_PATHS:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
    return None, None


VALIDATION_CASES = _load_generated_cases()
VALIDATION_SNAPSHOT, VALIDATION_SNAPSHOT_PATH = _load_validation_snapshot()


def _inject_ui_styles():
    st.markdown(
        """
        <style>
        :root {
            --ink: #16212f;
            --muted: #627086;
            --line: rgba(22, 33, 47, 0.10);
            --soft: #f5f1e8;
            --paper: #fbfaf7;
            --accent: #b4512d;
            --accent-dark: #7f3419;
            --teal: #176b6b;
            --sand: #ebe0c7;
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(180, 81, 45, 0.10), transparent 28%),
                radial-gradient(circle at top left, rgba(23, 107, 107, 0.10), transparent 24%),
                linear-gradient(180deg, #f8f5ee 0%, #fcfbf8 36%, #f5f0e4 100%);
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }

        h1, h2, h3 {
            color: var(--ink);
            letter-spacing: -0.02em;
        }

        .hero-shell {
            padding: 1.4rem 1.5rem 1.2rem;
            border: 1px solid var(--line);
            border-radius: 24px;
            background: linear-gradient(140deg, rgba(255,255,255,0.85), rgba(250,245,235,0.96));
            box-shadow: 0 18px 45px rgba(38, 44, 53, 0.08);
            margin-bottom: 1rem;
        }

        .hero-kicker {
            display: inline-block;
            padding: 0.28rem 0.6rem;
            border-radius: 999px;
            background: rgba(23, 107, 107, 0.10);
            color: var(--teal);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .hero-title {
            margin: 0.65rem 0 0.4rem;
            font-size: 2.15rem;
            font-weight: 800;
            color: var(--ink);
        }

        .hero-copy {
            color: var(--muted);
            font-size: 0.98rem;
            line-height: 1.6;
            margin: 0;
        }

        .mini-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 1rem;
        }

        .mini-card {
            padding: 0.85rem 0.95rem;
            border-radius: 18px;
            border: 1px solid var(--line);
            background: rgba(255,255,255,0.74);
        }

        .mini-label {
            color: var(--muted);
            font-size: 0.78rem;
            margin-bottom: 0.18rem;
        }

        .mini-value {
            color: var(--ink);
            font-size: 1.05rem;
            font-weight: 700;
        }

        .section-card {
            padding: 1rem 1.05rem;
            border-radius: 20px;
            border: 1px solid var(--line);
            background: rgba(255,255,255,0.76);
            margin-bottom: 0.9rem;
        }

        .section-title {
            font-size: 1rem;
            font-weight: 800;
            color: var(--ink);
            margin-bottom: 0.25rem;
        }

        .section-copy {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0;
        }

        .mode-panel {
            padding: 1rem 1.05rem;
            border-radius: 20px;
            border: 1px solid var(--line);
            margin-bottom: 0.9rem;
            background: linear-gradient(145deg, rgba(255,255,255,0.88), rgba(247,240,226,0.85));
        }

        .mode-panel.predictive {
            background: linear-gradient(145deg, rgba(255,255,255,0.90), rgba(224, 241, 241, 0.88));
        }

        .mode-badge {
            display: inline-block;
            padding: 0.24rem 0.52rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
            color: white;
            background: var(--accent);
        }

        .mode-panel.predictive .mode-badge {
            background: var(--teal);
        }

        .mode-title {
            color: var(--ink);
            font-size: 1.05rem;
            font-weight: 800;
            margin-bottom: 0.22rem;
        }

        .mode-copy {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0;
        }

        .toolbox-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.7rem;
        }

        .toolbox-chip {
            padding: 0.34rem 0.62rem;
            border-radius: 999px;
            background: rgba(22, 33, 47, 0.06);
            color: var(--ink);
            font-size: 0.8rem;
            font-weight: 600;
        }

        .toolbox-chip.on {
            background: rgba(180, 81, 45, 0.14);
            color: var(--accent-dark);
        }

        .result-banner {
            padding: 0.95rem 1rem;
            border-radius: 20px;
            border: 1px solid var(--line);
            background: linear-gradient(135deg, rgba(255,255,255,0.88), rgba(235,224,199,0.7));
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_hero():
    snapshot_cases = "-"
    snapshot_comp = "-"
    snapshot_mode = "-"
    if VALIDATION_SNAPSHOT:
        summary = VALIDATION_SNAPSHOT.get("summary", {})
        config = VALIDATION_SNAPSHOT.get("config", {})
        snapshot_cases = summary.get("case_count", "-")
        snapshot_comp = f"{summary.get('avg_comp_mae', 0.0):.3f}"
        snapshot_mode = config.get("mode", "-")
    st.markdown(
        f"""
        <div class="hero-shell">
            <div class="hero-kicker">Constrained Equilibrium Workspace</div>
            <div class="hero-title">Entrained-Flow Gasifier Model</div>
            <p class="hero-copy">
                把基础平衡求解、案例模板与 calibration toolbox 放进同一个工作台。
                `Prediction` 用于新工况试算，`Calibration` 用于贴合已有 plant / paper 数据。
            </p>
            <div class="mini-grid">
                <div class="mini-card">
                    <div class="mini-label">Validation Cases</div>
                    <div class="mini-value">{snapshot_cases}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">Current Avg Comp MAE</div>
                    <div class="mini-value">{snapshot_comp}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">Snapshot Mode</div>
                    <div class="mini-value">{snapshot_mode}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_mode_panel(run_mode, allow_heat_loss, allow_oc, allow_char):
    predictive = run_mode == "predictive"
    title = "Prediction Core" if predictive else "Calibration Toolbox"
    badge = "Predictive" if predictive else "Calibrated"
    copy = (
        "保持固定 closure 规则，不做逐案例反调。适合新工况、外推试算和看模型本体能力。"
        if predictive
        else "允许按你的目标启用 heat loss、O/C、char extent 等工具，用于案例贴合与参数诊断。"
    )
    chips = [
        ("HeatLoss", allow_heat_loss and not predictive),
        ("O/C", allow_oc and not predictive),
        ("CharExtent", allow_char and not predictive),
    ]
    chip_html = "".join(
        f'<span class="toolbox-chip {"on" if enabled else ""}">{label}</span>' for label, enabled in chips
    )
    st.markdown(
        f"""
        <div class="mode-panel {'predictive' if predictive else ''}">
            <div class="mode-badge">{badge}</div>
            <div class="mode-title">{title}</div>
            <p class="mode-copy">{copy}</p>
            <div class="toolbox-chip-row">{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_result_banner(run_mode, calibration_config):
    active_tools = []
    if calibration_config.allow_heat_loss_calibration:
        active_tools.append("HeatLoss")
    if calibration_config.allow_oc_calibration:
        active_tools.append("O/C")
    if calibration_config.allow_char_extent_search:
        active_tools.append("CharExtent")
    tool_text = " / ".join(active_tools) if active_tools else "无"
    mode_label = "Prediction" if run_mode == "predictive" else "Calibration"
    st.markdown(
        f"""
        <div class="result-banner">
            <div class="section-title">本次运行设置</div>
            <p class="section-copy">
                当前模式：<strong>{mode_label}</strong>；
                启用工具：<strong>{tool_text}</strong>。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- 1. 初始化 Session State (保持不变) ---
def init_session_state():
    defaults = {
        # Coal
        "Cd": 75.83, "Hd": 4.58, "Od": 10.89, "Nd": 1.19, "Sd": 0.29, "Ad": 7.22,
        "Vd": 34.96, "FCd": 57.82, "Mt": 14.3, "HHV_Input": 30720.0,
        "HHV_Method": 0, # 0: Input, 1: Formula
        # Process
        "FeedRate": 1000.0,
        "SlurryConc": 60.0,
        "Ratio_OC": 1.0,
        "Ratio_SC": 0.08,
        "pt": 99.6,
        "P": 4.0,
        "TIN": 300.0,
        "HeatLossPercent": 3.0,
        "TR": 1500.0,
        "T_Scrubber": 210.0,
        "GasifierType": "Dry Powder",
        "Target_T": 1370.0,
        "SolverMethod": "Stoic",
        "DeltaT_WGS": 0.0,
        "DeltaT_Meth": 0.0,
        "HeatLossMode": TUNED_19CASES_PROFILE["HeatLossMode"],
        "CarbonConversionMode": TUNED_19CASES_PROFILE["CarbonConversionMode"],
        "DeltaTMode": TUNED_19CASES_PROFILE["DeltaTMode"],
        "CharExtentMode": TUNED_19CASES_PROFILE["CharExtentMode"],
        "advanced_mode": False,
        "use_tuned_profile": True,
        "use_auto_strategy": True,
        "run_mode": "predictive",
        "tool_allow_heat_loss_calibration": True,
        "tool_allow_oc_calibration": True,
        "tool_allow_char_extent_search": True,
        "toolbox_preset": "Balanced Fit",
        "selected_validation_case": "保持当前 (Custom)",
        "last_case_name": None,
        # 激冷湿合成气计算器（独立模块，与 quench_syngas 默认一致）
        "quench_V_dry": 5647.0,
        "quench_T_gas_in": 1397.0,
        "quench_P_total": 1.6013,
        "quench_Cp_gas": 2.31,
        "quench_T_water_in": DEFAULT_T_WATER_IN_CELSIUS,
        "quench_cooling_water_flow_kg_h": DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
        "quench_water_saturated": False,
        "quench_H_water_override": None,
        "quench_T_bracket_low": 50.0,
        "quench_T_bracket_high": 300.0,
        "quench_trial_T": 175.0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _collect_input_data_from_state():
    keys = [
        "Cd", "Hd", "Od", "Nd", "Sd", "Ad", "Vd", "FCd", "Mt", "HHV_Input", "HHV_Method",
        "FeedRate", "SlurryConc", "Ratio_OC", "Ratio_SC", "pt", "P", "TIN", "TR",
        "HeatLossPercent", "GasifierType", "SolverMethod", "DeltaT_WGS", "DeltaT_Meth",
        "HeatLossMode", "CarbonConversionMode", "DeltaTMode", "CharExtentMode",
    ]
    return {key: st.session_state[key] for key in keys if key in st.session_state}


def _apply_case_to_session(case_name):
    if case_name not in VALIDATION_CASES:
        return
    case = VALIDATION_CASES[case_name]
    inputs = build_profile_inputs(case, profile="tuned-19cases" if st.session_state.use_tuned_profile else None)
    for key, value in inputs.items():
        st.session_state[key] = value
    st.session_state.selected_validation_case = case_name
    st.session_state.last_case_name = case_name


def _get_snapshot_record(case_name):
    if not VALIDATION_SNAPSHOT or not case_name or case_name == "保持当前 (Custom)":
        return None
    records = VALIDATION_SNAPSHOT.get("records", [])
    for record in records:
        if record.get("case") == case_name:
            return record
    return None


def _build_validation_rows(results, expected):
    rows = []
    metric_pairs = [
        ("Temperature (°C)", "TOUT_C", "TOUT_C"),
        ("CO (dry%)", "Y_CO_dry", "Y_CO"),
        ("H2 (dry%)", "Y_H2_dry", "Y_H2"),
        ("CO2 (dry%)", "Y_CO2_dry", "Y_CO2"),
        ("CH4 (dry%)", "Y_CH4_dry", "Y_CH4"),
    ]
    for label, pred_key, exp_key in metric_pairs:
        target = expected.get(exp_key)
        pred = results.get(pred_key)
        if target is None and label.startswith("Temperature"):
            continue
        rows.append(
            {
                "Metric": label,
                "Model Result": pred,
                "Paper/Target": target,
                "Abs Error": None if target is None else abs(pred - target),
            }
        )
    return pd.DataFrame(rows)


def _render_validation_overview_tab():
    st.subheader("19 案验证总览")
    if not VALIDATION_SNAPSHOT:
        st.warning("未找到验证快照，请先运行 audit 脚本生成 `generated/validation/validation_results.json`。")
        return

    summary = VALIDATION_SNAPSHOT.get("summary", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("案例数", summary.get("case_count", "-"))
    c2.metric("平均组成误差", f"{summary.get('avg_comp_mae', 0.0):.4f}")
    c3.metric("平均温度绝对误差", f"{summary.get('avg_temp_abs_error_C', 0.0):.4g} °C")
    c4.metric("最终告警", f"{summary.get('avg_final_warnings', 0.0):.1f}")

    if VALIDATION_SNAPSHOT_PATH:
        st.caption(f"快照来源：`{VALIDATION_SNAPSHOT_PATH.relative_to(PROJECT_ROOT)}`")

    top_problem_cases = pd.DataFrame(summary.get("top_problem_cases", []))
    if not top_problem_cases.empty:
        st.markdown("#### 当前最差案例")
        st.dataframe(top_problem_cases, hide_index=True, use_container_width=True)

    config = VALIDATION_SNAPSHOT.get("config", {})
    if config:
        with st.expander("当前验证设置", expanded=False):
            calibration_config = config.get("calibration_config", {})
            st.dataframe(
                pd.DataFrame(
                    [
                        {"项目": "验证方案", "说明": config.get("profile", "tuned-19cases")},
                        {"项目": "运行模式", "说明": config.get("mode", "calibrated")},
                        {"项目": "求解器", "说明": config.get("solver_method") or "Stoic"},
                        {"项目": "热损校准", "说明": "开启" if config.get("calibrate_heat_loss") else "关闭"},
                        {"项目": "Toolbox", "说明": "开启" if config.get("toolbox_enabled") else "关闭"},
                        {"项目": "Char extent", "说明": config.get("char_extent_mode") or "-"},
                        {"项目": "HeatLoss 校准", "说明": "开启" if calibration_config.get("allow_heat_loss_calibration") else "关闭"},
                        {"项目": "O/C 校准", "说明": "开启" if calibration_config.get("allow_oc_calibration") else "关闭"},
                        {"项目": "Char 搜索", "说明": "开启" if calibration_config.get("allow_char_extent_search") else "关闭"},
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )

# --- 2. 核心逻辑封装 ---
def run():
    """
    封装的主运行函数，供 chem_portal 调用
    """
    init_session_state()
    _inject_ui_styles()

    _render_page_hero()
    st.markdown("[查看 README](https://github.com/dachou5224/gasifier-equilibrium-model/blob/main/README.md)")
    st.divider()

    tab_gas, tab_validation, tab_quench = st.tabs(["Gasifier Workbench", "Validation Snapshot", "Quench Calculator"])

    with tab_gas:
        _render_gasifier_tab()
    with tab_validation:
        _render_validation_overview_tab()
    with tab_quench:
        _render_quench_syngas_tab()


def _render_gasifier_tab():
    """主气化炉平衡模型界面。"""
    init_session_state()

    with st.expander("📖 本地中文操作手册 (使用前必读)", expanded=False):
        st.markdown("""
        **【模型定位】**：本页面为 **全局热力学平衡模型**。页面已经内置推荐设置，普通使用者无需理解求解器细节，只需选择模板并运行。

        **【核心摇杆解析】**
        *   **氧煤比 (O/C)**：决定放热强度，是温度与有效气之间的第一操纵杆。
        *   **汽煤比 (S/C)**：主要影响 H2 / CO2 / 温度之间的平衡。
        *   **总热损 (%)**：在当前模型里拆解为“物理热损 + 模型修正项”，不再等同于单纯壁散热。

        **【进阶玩法建议】**
        *   **模板工况模式**：优先使用文献模板，减少无效调参。
        *   **自定义模式**：若做工程试算，可直接修改 O/C、S/C、压力和煤质。
        """)

    col_input, col_result = st.columns([1.2, 2.8], gap="medium")
    case_options = ["保持当前 (Custom)"] + list(VALIDATION_CASES.keys())

    with col_input:
        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">快速开始</div>
                <p class="section-copy">
                    推荐顺序是：先选 benchmark 模板，再确定是做预测还是做贴合，最后只改 O/C、S/C、压力和热损。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown("#### 1. 参考模板")
            st.caption(f"当前优先读取 `generated/validation_cases_from_kinetic.json` 中的 {len(VALIDATION_CASES)} 个 benchmark 工况。")
            case_name = st.selectbox(
                "选择工况",
                case_options,
                index=case_options.index(st.session_state.selected_validation_case)
                if st.session_state.selected_validation_case in case_options
                else 0,
                label_visibility="collapsed",
            )
            st.session_state.selected_validation_case = case_name
            if case_name != "保持当前 (Custom)" and st.session_state.last_case_name != case_name:
                _apply_case_to_session(case_name)
                st.rerun()
            st.session_state.use_tuned_profile = True
            st.session_state.use_auto_strategy = True

            if case_name != "保持当前 (Custom)" and st.button("预填该工况", type="secondary", use_container_width=True):
                _apply_case_to_session(case_name)
                st.success(f"已应用模板：{case_name}")
                st.rerun()

        st.markdown("#### 2. 运行模式")
        mode_label = st.radio(
            "运行模式",
            ["Prediction", "Calibration"],
            index=0 if st.session_state.run_mode == "predictive" else 1,
            horizontal=True,
            help="Prediction 禁用逐案例校准，适合新工况预测；Calibration 启用 toolbox 拟合已有案例。",
        )
        st.session_state.run_mode = "predictive" if mode_label == "Prediction" else "calibrated"

        if st.session_state.run_mode == "predictive":
            st.session_state.toolbox_preset = "Manual"
            _render_mode_panel(
                st.session_state.run_mode,
                st.session_state.tool_allow_heat_loss_calibration,
                st.session_state.tool_allow_oc_calibration,
                st.session_state.tool_allow_char_extent_search,
            )
            st.info("当前为 `Prediction`。页面只保留模型本体与固定 closure，不做逐案例反调。")
        else:
            preset = st.radio(
                "Toolbox Preset",
                ["Temperature Match", "Balanced Fit", "Full Calibration", "Manual"],
                index=["Temperature Match", "Balanced Fit", "Full Calibration", "Manual"].index(
                    st.session_state.toolbox_preset
                    if st.session_state.toolbox_preset in {"Temperature Match", "Balanced Fit", "Full Calibration", "Manual"}
                    else "Balanced Fit"
                ),
                horizontal=True,
                help="先用 preset 选策略，再按需手动微调具体工具。",
            )
            st.session_state.toolbox_preset = preset
            if preset == "Temperature Match":
                st.session_state.tool_allow_heat_loss_calibration = True
                st.session_state.tool_allow_oc_calibration = False
                st.session_state.tool_allow_char_extent_search = False
            elif preset == "Balanced Fit":
                st.session_state.tool_allow_heat_loss_calibration = False
                st.session_state.tool_allow_oc_calibration = True
                st.session_state.tool_allow_char_extent_search = True
            elif preset == "Full Calibration":
                st.session_state.tool_allow_heat_loss_calibration = True
                st.session_state.tool_allow_oc_calibration = True
                st.session_state.tool_allow_char_extent_search = True

            st.caption(
                "建议：只关心温度先用 `Temperature Match`；需要更贴合组分时再用 `Balanced Fit` 或 `Full Calibration`。"
            )
            c_tool_1, c_tool_2, c_tool_3 = st.columns(3)
            st.session_state.tool_allow_heat_loss_calibration = c_tool_1.checkbox(
                "HeatLoss",
                value=st.session_state.tool_allow_heat_loss_calibration,
            )
            st.session_state.tool_allow_oc_calibration = c_tool_2.checkbox(
                "O/C",
                value=st.session_state.tool_allow_oc_calibration,
            )
            st.session_state.tool_allow_char_extent_search = c_tool_3.checkbox(
                "CharExtent",
                value=st.session_state.tool_allow_char_extent_search,
            )
            _render_mode_panel(
                st.session_state.run_mode,
                st.session_state.tool_allow_heat_loss_calibration,
                st.session_state.tool_allow_oc_calibration,
                st.session_state.tool_allow_char_extent_search,
            )

        st.markdown("#### 3. 核心操纵杆")
        st.session_state.GasifierType = st.radio(
            "气化炉水设置",
            ["Dry Powder", "CWS"],
            index=0 if st.session_state.GasifierType == "Dry Powder" else 1,
            horizontal=True,
        )
        
        c_feed, c_p = st.columns(2)
        if st.session_state.GasifierType == "Dry Powder":
            st.session_state.FeedRate = c_feed.number_input("干煤投料 (kg/h)", value=float(st.session_state.FeedRate))
        else:
            st.session_state.FeedRate = c_feed.number_input("煤浆流量 (kg/h)", value=float(st.session_state.FeedRate))
            st.session_state.SlurryConc = st.number_input("水煤浆浓度 (wt%)", value=float(st.session_state.SlurryConc))

        st.session_state.P = c_p.number_input("系统压力 (MPa)", value=float(st.session_state.P), step=0.1)
        
        c3, c4 = st.columns(2)
        st.session_state.Ratio_OC = c3.number_input("氧煤比 (O/C)", value=float(st.session_state.Ratio_OC), format="%.3f", step=0.01)
        st.session_state.Ratio_SC = c4.number_input("汽煤比 (S/C)", value=float(st.session_state.Ratio_SC), format="%.3f", step=0.01)
        
        st.session_state.HeatLossPercent = st.number_input(
            "总热损 (%)",
            value=float(st.session_state.HeatLossPercent),
            format="%.2f",
            step=0.5,
            help="页面内部会自动使用推荐热损逻辑；这里显示的是最终使用的总热损。",
        )

        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">如何选工具</div>
                <p class="section-copy">
                    HeatLoss 更像能量闭合修正；O/C 与 CharExtent 更直接影响组分分配。
                    如果你在做验证池外预测，先保持 `Prediction`；只有拿到 plant / paper 对照值时，再进入 `Calibration`。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        advanced_mode = st.toggle("🛠️ 显示高级配置 (底层煤质/反应器约束)", value=st.session_state.get('advanced_mode', False))
        st.session_state.advanced_mode = advanced_mode

        if advanced_mode:
            with st.expander("🪨 详细煤质分析", expanded=True):
                selected_db_coal = st.selectbox("从内置库填入煤", ["None"] + list(COAL_DATABASE.keys()))
                if selected_db_coal != "None":
                    if st.button(f"应用 {selected_db_coal}"):
                        db_data = COAL_DATABASE[selected_db_coal]
                        for k, v in db_data.items():
                            if k in st.session_state: st.session_state[k] = v
                        if 'HHV_d' in db_data:
                            st.session_state['HHV_Input'] = db_data['HHV_d'] * 1000.0
                        st.rerun()

                c1, c2 = st.columns(2)
                st.session_state.Cd = c1.number_input("C", value=float(st.session_state.Cd), format="%.2f")
                st.session_state.Hd = c2.number_input("H", value=float(st.session_state.Hd), format="%.2f")
                st.session_state.Od = c1.number_input("O", value=float(st.session_state.Od), format="%.2f")
                st.session_state.Nd = c2.number_input("N", value=float(st.session_state.Nd), format="%.2f")
                st.session_state.Sd = c1.number_input("S", value=float(st.session_state.Sd), format="%.2f")
                st.session_state.Ad = c2.number_input("Ash", value=float(st.session_state.Ad), format="%.2f")
                st.session_state.Mt = st.number_input("Total Moisture (wt%)", value=float(st.session_state.Mt), format="%.2f")

                hhv_mode = st.radio("HHV 来源", ["Input", "NICE1 Formula"], 
                                    index=st.session_state.HHV_Method, horizontal=True)
                st.session_state.HHV_Method = 0 if hhv_mode == "Input" else 1
                
                if st.session_state.HHV_Method == 0:
                    st.session_state.HHV_Input = st.number_input("HHV (kJ/kg, Dry)", value=float(st.session_state.HHV_Input))

            with st.expander("🏭 附加管道条件", expanded=True):
                st.session_state.TIN = st.number_input("入口 T (K)", value=float(st.session_state.TIN))
                st.session_state.pt = st.number_input("氧纯度 (%)", value=float(st.session_state.pt))
            
            with st.expander("🛠️ 温度校准", expanded=False):
                st.session_state.Target_T = st.number_input("预估目标 T (°C)", value=float(st.session_state.Target_T))
                
                if st.button("仅按目标温度反算热损", use_container_width=True):
                    input_data = _collect_input_data_from_state()
                    try:
                        model = GasifierModel(input_data)
                        target_K = st.session_state.Target_T + 273.15
                        with st.spinner("Calibrating..."):
                            loss, _ = model.calculate_heat_loss_for_target_T(target_K)
                            st.session_state.HeatLossPercent = loss
                            st.success(f"校正成功: 新热损 {loss:.4f}%")
                        st.rerun()
                    except Exception as e:
                        st.error(f"校正失败: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🚀 开始计算", type="primary", use_container_width=True)

    with col_result:
        if run_btn:
            try:
                input_data = _collect_input_data_from_state()
                expected = None
                calibration_config = build_calibration_config(
                    st.session_state.run_mode,
                    allow_heat_loss_calibration=st.session_state.tool_allow_heat_loss_calibration if st.session_state.run_mode == "calibrated" else False,
                    allow_oc_calibration=st.session_state.tool_allow_oc_calibration if st.session_state.run_mode == "calibrated" else False,
                    allow_char_extent_search=st.session_state.tool_allow_char_extent_search if st.session_state.run_mode == "calibrated" else False,
                )
                with st.spinner("Solving equilibrium..."):
                    if case_name != "保持当前 (Custom)" and st.session_state.use_auto_strategy:
                        expected = VALIDATION_CASES[case_name]["expected_output"]
                        _, model, _, res, _ = select_best_validation_candidate(
                            input_data,
                            expected,
                            calibrate_heat_loss=calibration_config.allow_heat_loss_calibration,
                            mode=st.session_state.run_mode,
                            calibration_config=calibration_config,
                        )
                    else:
                        model = GasifierModel(input_data)
                        res = model.run_simulation()

                st.session_state.last_gasifier_Vg_dry = res["Vg_dry"]
                st.session_state.last_gasifier_TOUT_C = res["TOUT_C"]
                st.session_state.last_gasifier_P_MPa = float(model.inputs.get("P", st.session_state.P))
                
                st.success("计算完成")
                _render_result_banner(st.session_state.run_mode, calibration_config)

                st.subheader("1. 关键性能指标")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("出口温度", f"{res['TOUT_C']:.1f} °C", delta=f"{res['Heat_Err_Pct']:.3f}% Err")
                kpi2.metric("有效气 (CO+H2)", f"{res['Y_CO_dry']+res['Y_H2_dry']:.1f} %")
                kpi3.metric("干气流量", f"{res['Vg_dry']:.0f} Nm³/h")
                kpi4.metric("水气比 (W/G)", f"{res['WGR_Quench']:.3f}")

                st.subheader("2. 合成气组成")
                comp_data = {
                    "组分": ["CO", "H2", "CO2", "CH4", "N2", "H2O"],
                    "干基 (Dry vol%)": [
                        res['Y_CO_dry'], res['Y_H2_dry'], res['Y_CO2_dry'], 
                        res['Y_CH4_dry'], res['Y_N2_dry'], 0.0
                    ],
                    "湿基 (Wet vol%)": [
                        res['Y_CO_wet'], res['Y_H2_wet'], res['Y_CO2_wet'], 
                        res['Y_CH4_wet'], res['Y_N2_wet'], res['Y_H2O_wet']
                    ]
                }
                df_comp = pd.DataFrame(comp_data)
                
                c_table, c_chart = st.columns([1, 1])
                with c_table:
                    st.dataframe(df_comp.round(2), hide_index=True, use_container_width=True)
                    
                with c_chart:
                    fig = go.Figure(data=[go.Pie(labels=df_comp["组分"], 
                                                 values=df_comp["干基 (Dry vol%)"], 
                                                 hole=.4,
                                                 title="干基组成")])
                    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=220)
                    st.plotly_chart(fig, use_container_width=True)

                st.subheader("3. 运行摘要")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"项目": "出口温度", "数值": f"{res['TOUT_C']:.2f} °C"},
                            {"项目": "总热损", "数值": f"{float(model.inputs.get('HeatLossPercent', 0.0)):.3f} %"},
                            {"项目": "氧煤比", "数值": f"{float(model.inputs.get('Ratio_OC', 0.0)):.4f}"},
                            {"项目": "汽煤比", "数值": f"{float(model.inputs.get('Ratio_SC', 0.0)):.4f}"},
                            {"项目": "残余固碳", "数值": f"{float(res.get('ResidualCarbonMol', 0.0)):.2f} mol"},
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

                st.subheader(f"4. 激冷/水洗 (@{st.session_state.T_Scrubber}°C)")
                st.info(f"💧 饱和湿气流量: **{res['Vg_Quench']:.1f} Nm³/h** | 水气比: **{res['WGR_Quench']:.3f}** (mol/mol)")
                
                with st.expander("🔬 能量与元素平衡诊断"):
                    d1, d2, d3, d4 = st.columns(4)
                    d1.write(f"**热平衡误差:** {res['Heat_Err_Pct']:.4f}%")
                    d2.write(f"**碳平衡误差:** {res['ERR_C']:.4f}%")
                    d3.write(f"**计算 HHV:** {res['HHV']:.2f} kJ/kg")
                    d4.write(f"**残余固碳:** {res.get('ResidualCarbonMol', 0.0):.2f} mol")

                if case_name != "保持当前 (Custom)":
                    expected = expected or VALIDATION_CASES[case_name]["expected_output"]
                    st.subheader("5. 与当前验证工况对比")
                    st.dataframe(_build_validation_rows(res, expected).round(4), hide_index=True, use_container_width=True)

                    snapshot_record = _get_snapshot_record(case_name)
                    if snapshot_record:
                        with st.expander("查看该模板最近的验证记录", expanded=False):
                            c1, c2, c3 = st.columns(3)
                            c1.metric("平均组成误差", f"{float(snapshot_record.get('score', {}).get('comp_mae') or 0.0):.4f}")
                            c2.metric("使用 O/C", f"{float(snapshot_record.get('ratio_oc_used') or 0.0):.4f}")
                            c3.metric("使用热损", f"{float(snapshot_record.get('effective_heat_loss_percent') or 0.0):.3f} %")
                            st.dataframe(
                                pd.DataFrame(
                                    [
                                        {
                                            "项目": "出口温度 (°C)",
                                            "最近验证值": snapshot_record.get("predicted", {}).get("TOUT_C"),
                                            "目标值": snapshot_record.get("expected", {}).get("TOUT_C"),
                                            "误差": snapshot_record.get("errors", {}).get("T_error_C"),
                                        },
                                        {
                                            "项目": "CO (dry%)",
                                            "最近验证值": snapshot_record.get("predicted", {}).get("Y_CO"),
                                            "目标值": snapshot_record.get("expected", {}).get("Y_CO"),
                                            "误差": snapshot_record.get("errors", {}).get("Y_CO_error"),
                                        },
                                        {
                                            "项目": "H2 (dry%)",
                                            "最近验证值": snapshot_record.get("predicted", {}).get("Y_H2"),
                                            "目标值": snapshot_record.get("expected", {}).get("Y_H2"),
                                            "误差": snapshot_record.get("errors", {}).get("Y_H2_error"),
                                        },
                                        {
                                            "项目": "CO2 (dry%)",
                                            "最近验证值": snapshot_record.get("predicted", {}).get("Y_CO2"),
                                            "目标值": snapshot_record.get("expected", {}).get("Y_CO2"),
                                            "误差": snapshot_record.get("errors", {}).get("Y_CO2_error"),
                                        },
                                        {
                                            "项目": "CH4 (dry%)",
                                            "最近验证值": snapshot_record.get("predicted", {}).get("Y_CH4"),
                                            "目标值": snapshot_record.get("expected", {}).get("Y_CH4"),
                                            "误差": snapshot_record.get("errors", {}).get("Y_CH4_error"),
                                        },
                                    ]
                                ).round(4),
                                hide_index=True,
                                use_container_width=True,
                            )

            except Exception as e:
                st.error(f"Simulation Failed: {e}")
                st.exception(e)

        else:
            st.info("👈 请在左侧配置煤质和工艺参数，然后点击 **开始计算**。")
            st.caption("当前页面已内置推荐设置，并优先读取最新验证工况模板。")


def _render_quench_syngas_tab():
    """激冷后湿合成气平衡温度：独立计算器（quench_syngas）。"""
    init_session_state()

    st.markdown(
        "根据干气显热与蒸发吸热平衡，求解 **激冷后出口温度**（T_out）。"
        " 饱和水蒸气分压与汽/液焓来自内置蒸汽表插值。"
    )
    st.caption(
        "默认激冷水温度与流量与 `quench_syngas` 一致；可将「饱和液态水」用于高温进水（如 180℃）。"
    )

    col_in, col_out = st.columns([1.2, 2.8], gap="medium")

    with col_in:
        st.subheader("输入")
        if st.button("从上次气化炉结果填入", help="需先在「气化炉平衡」页成功运行一次计算"):
            v = st.session_state.get("last_gasifier_Vg_dry")
            if v is not None:
                st.session_state.quench_V_dry = float(v)
                st.session_state.quench_T_gas_in = float(st.session_state.get("last_gasifier_TOUT_C", 1397.0))
                st.session_state.quench_P_total = float(st.session_state.get("last_gasifier_P_MPa", 1.6013))
                st.success("已填入干气流量、出口温度、系统压力")
                st.rerun()
            else:
                st.warning("尚无气化炉计算结果，请先运行主模型。")

        st.session_state.quench_V_dry = st.number_input(
            "干合成气流量 V_dry (Nm³/h)",
            min_value=1.0,
            value=float(st.session_state.quench_V_dry),
            format="%.1f",
        )
        st.session_state.quench_T_gas_in = st.number_input(
            "干气进口温度 (°C)",
            min_value=0.0,
            max_value=2000.0,
            value=float(st.session_state.quench_T_gas_in),
            format="%.1f",
        )
        st.session_state.quench_P_total = st.number_input(
            "系统总压力 P（绝压, MPa.a）",
            min_value=0.001,
            value=float(st.session_state.quench_P_total),
            format="%.4f",
            step=0.01,
        )
        st.session_state.quench_Cp_gas = st.number_input(
            "干气平均体积比热 Cp (kJ/(Nm³·℃))",
            min_value=0.01,
            value=float(st.session_state.quench_Cp_gas),
            format="%.3f",
            step=0.01,
        )
        st.markdown("**激冷水**")
        st.session_state.quench_T_water_in = st.number_input(
            "激冷水温度 (°C)",
            value=float(st.session_state.quench_T_water_in),
            format="%.1f",
        )
        st.session_state.quench_cooling_water_flow_kg_h = st.number_input(
            "激冷水质量流量 (kg/h)",
            min_value=0.0,
            value=float(st.session_state.quench_cooling_water_flow_kg_h),
            format="%.1f",
            help="设为 0 表示不校核流量（内部按 None 处理）",
        )
        st.session_state.quench_water_saturated = st.checkbox(
            "进水为饱和液态水（用 h' 查表）",
            value=bool(st.session_state.quench_water_saturated),
        )

        use_h_override = st.checkbox(
            "手动指定进口水比焓 H（kJ/kg）",
            value=st.session_state.quench_H_water_override is not None,
        )
        if use_h_override:
            h_def = float(st.session_state.quench_H_water_override or 175.6)
            st.session_state.quench_H_water_override = st.number_input(
                "H_water_in (kJ/kg)",
                value=h_def,
                format="%.2f",
            )
        else:
            st.session_state.quench_H_water_override = None

        st.markdown("**求根区间 (°C)**")
        c_lo, c_hi = st.columns(2)
        st.session_state.quench_T_bracket_low = c_lo.number_input(
            "下限",
            value=float(st.session_state.quench_T_bracket_low),
            format="%.1f",
        )
        st.session_state.quench_T_bracket_high = c_hi.number_input(
            "上限",
            value=float(st.session_state.quench_T_bracket_high),
            format="%.1f",
        )

        st.session_state.quench_trial_T = st.number_input(
            "试算温度（仅用于试算表）",
            value=float(st.session_state.quench_trial_T),
            format="%.1f",
        )

        run_quench = st.button("求解平衡出口温度", type="primary", use_container_width=True)
        trial_btn = st.button("仅试算当前假定温度", use_container_width=True)

    flow_kw = st.session_state.quench_cooling_water_flow_kg_h
    flow_arg = None if flow_kw <= 0 else float(flow_kw)

    with col_out:
        st.subheader("结果")
        st.caption("ΔQ = Q_release − Q_absorb，平衡时 ΔQ → 0")

        if trial_btn:
            try:
                st_trial = evaluate_quench_syngas(
                    float(st.session_state.quench_trial_T),
                    float(st.session_state.quench_V_dry),
                    float(st.session_state.quench_T_gas_in),
                    float(st.session_state.quench_P_total),
                    float(st.session_state.quench_Cp_gas),
                    T_water_in_celsius=float(st.session_state.quench_T_water_in),
                    H_water_in_kj_kg=st.session_state.quench_H_water_override,
                    water_inlet_saturated_liquid=bool(st.session_state.quench_water_saturated),
                    cooling_water_mass_flow_kg_h=flow_arg,
                )
                st.info(f"假定 T_out = **{st.session_state.quench_trial_T:.2f} °C**")
                _show_quench_state(st_trial)
            except Exception as e:
                st.error(str(e))
                st.exception(e)

        if run_quench:
            try:
                T_hi = float(st.session_state.quench_T_bracket_high)
                T_lo = float(st.session_state.quench_T_bracket_low)
                if T_lo >= T_hi:
                    st.error("求根区间无效：下限须小于上限。")
                else:
                    T_out, st_f = solve_wet_syngas_temperature_after_quench(
                        float(st.session_state.quench_V_dry),
                        float(st.session_state.quench_T_gas_in),
                        float(st.session_state.quench_P_total),
                        float(st.session_state.quench_Cp_gas),
                        T_water_in_celsius=float(st.session_state.quench_T_water_in),
                        H_water_in_kj_kg=st.session_state.quench_H_water_override,
                        water_inlet_saturated_liquid=bool(st.session_state.quench_water_saturated),
                        cooling_water_mass_flow_kg_h=flow_arg,
                        T_bracket_low_c=T_lo,
                        T_bracket_high_c=T_hi,
                    )
                    st.success(f"平衡出口温度 **T_out = {T_out:.4f} °C**")
                    _show_quench_state(st_f)
            except Exception as e:
                st.error(str(e))
                st.exception(e)

        if not trial_btn and not run_quench:
            st.info("👈 填写左侧参数后点击 **求解** 或 **试算**。")


def _show_quench_state(state):
    """展示 QuenchSyngasState 为表格 + 指标（参数勿用名 st，以免遮蔽 streamlit）。"""
    d = state.to_dict()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("T_out", f"{d['T_out_C']:.3f} °C")
    m2.metric("y_H2O", f"{d['y_H2O']*100:.2f} %")
    m3.metric("ΔQ", f"{d['delta_Q_kJ_h']:.0f} kJ/h")
    m4.metric(
        "蒸发量 vs 流量",
        "✓" if d["evaporation_within_flow_limit"] else "不足",
    )
    rows = [
        ("饱和蒸汽压 P_sat", f"{d['P_sat_MPa_a']:.6f} MPa.a"),
        ("蒸发水体积流量 V_H2O", f"{d['V_H2O_Nm3_h']:.2f} Nm³/h"),
        ("蒸发水质量流量 m_H2O", f"{d['m_H2O_kg_h']:.2f} kg/h"),
        ("饱和蒸汽比焓 h''", f"{d['H_vapor_kJ_kg']:.2f} kJ/kg"),
        ("Q_release", f"{d['Q_release_kJ_h']:.0f} kJ/h"),
        ("Q_absorb", f"{d['Q_absorb_kJ_h']:.0f} kJ/h"),
        ("激冷水进口焓（解析）", f"{d['H_water_in_kJ_kg']:.2f} kJ/kg"),
        ("激冷水温度（输入）", f"{d['T_water_in_C']:.2f} °C"),
        (
            "激冷水流量（kg/h）",
            "不校核" if d["cooling_water_mass_flow_kg_h"] is None else f"{d['cooling_water_mass_flow_kg_h']:.1f}",
        ),
    ]
    st.table(pd.DataFrame(rows, columns=["量", "数值"]))


# --- 3. 脚本入口 ---
if __name__ == "__main__":
    st.set_page_config(page_title="EFG Dev", layout="wide")
    run()
