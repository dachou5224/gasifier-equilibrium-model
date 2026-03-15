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
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys
import os

# Add src to path so we can import gasifier package
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from gasifier.coal_props import COAL_DATABASE
from gasifier.validation_cases import VALIDATION_CASES

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
        "Ratio_OC": 1.0, # Updated default
        "Ratio_SC": 0.08,
        "pt": 99.6,
        "P": 4.0,
        "TIN": 300.0,
        "HeatLossPercent": 1.0,
        "TR": 1500.0,
        "T_Scrubber": 210.0,
        "GasifierType": "Dry Powder",
        "Target_T": 1370.0, # 校正目标温度
        "SolverMethod": "RGibbs", # RGibbs or Stoic
        "DeltaT_WGS": 0.0,
        "DeltaT_Meth": 0.0,
        "advanced_mode": False
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# --- 2. 核心逻辑封装 ---
def run():
    """
    封装的主运行函数，供 chem_portal 调用
    """
    init_session_state()

    # 标题区域
    st.title("🏭 气流床气化炉平衡模型")
    st.markdown("Thermodynamic equilibrium simulation based on Gibbs Free Energy Minimization.")
    st.markdown("[📖 查看项目文档 (README) & 算法说明](https://github.com/dachou5224/gasifier-equilibrium-model/blob/main/README.md)")
    
    st.divider()

    with st.expander("📖 本地中文操作手册 (使用前必读)", expanded=False):
        st.markdown("""
        **【模型定位】**：本页面为 **全局热力学平衡模型**（基于最小 Gibbs 自由能法）。它并不关心反应需要耗时多久、管道有多长，它只推演*在无限长时间下，当前配比能达到的能量与产率极值*。非常适合做气化炉的大尺度物料衡算与理论宏观上限预估。

        **【核心摇杆解析】**
        *   **氧煤比 (O/C)**：控制着系统反应的底色。**调高 O/C** 会促进煤炭燃烧释放海量热能，直接拉高炉温（但会使 CO 氧化为 $CO_2$ 导致有效气下降）；**调低 O/C** 有利于保护有效气，但可能因吸热的气化反应导致热量亏空，系统死机（未转化碳激增）。
        *   **汽煤比 (S/C)**：水蒸气的加入有助于发生水煤气变换反应（WGS：$CO+H_2O \\rightleftharpoons CO_2+H_2$），能提升产气中的氢气占比，但因为气化反应属于强吸热，过多的汽煤比会拉低全炉操作温度。
        *   **热损估测 (%)**：气流床通常的热损约为 1%~5%（视规模而定）。如果在配置中你**不知道该怎么设**，请留在这里，然后打开下方的【🛠️ 显示高级配置】->【🛠️ 智能热量反算】，输入你的主观期望温度（如 1350°C），算法能反算出如果要维持这个温度，当前系统能承受多大的热损。

        **【进阶玩法建议】**
        *   **解禁底层配置**：点击表单下方的 `[🛠️ 显示高级配置]` 可以亲自调节你那批实验煤的高低位热值、全元素分析参数以及管道入口的预热设定。
        *   **切换弱反应器**：默认推荐 `RGibbs` 求全局最优点。但如果你觉得实际炉子温度过低，部分反应（如甲烷化）达不到理想平衡点，可以切成 `Stoic` 算法并植入温差（Approach Temp）来约束它们。
        """)

    # [关键修改] 使用列布局代替 Sidebar
    # 左侧 (1.2): 参数输入区 | 右侧 (2.8): 结果展示区
    col_input, col_result = st.columns([1.2, 2.8], gap="medium")

    # ==========================================
    # 左侧：参数配置区域
    # ==========================================
    with col_input:
        st.info("🎯 **引导式操作面板 (Minimalist Mode)**")
        
        # 1. 验证工况加载
        with st.container(border=True):
            st.markdown("#### 📂 步骤 1. 选择参考模板")
            st.caption("建议以此为工业基准起步，大幅缩少不必要的调参。")
            case_name = st.selectbox("选择工况:", ["保持当前 (Custom)"] + list(VALIDATION_CASES.keys()), label_visibility="collapsed")
            
            if case_name != "保持当前 (Custom)" and st.button("预填该工况", type="secondary", use_container_width=True):
                data = VALIDATION_CASES[case_name]["inputs"]
                c_data = data["Coal Analysis"]
                if c_data == "SAME_AS_BASE":
                    c_data = VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]["Coal Analysis"]
                for k, v in c_data.items():
                    if k in st.session_state: st.session_state[k] = v
                p_data = data["Process Conditions"]
                for k, v in p_data.items():
                    if k in st.session_state: st.session_state[k] = v
                st.success(f"已应用 {case_name}")
                st.rerun()

        # 核心参数面板
        st.markdown("#### 🎛️ 步骤 2. 核心操纵杆")
        st.session_state.GasifierType = st.radio("气化炉水设置", ["Dry Powder", "CWS"], 
                                                     index=0 if st.session_state.GasifierType=="Dry Powder" else 1, horizontal=True)
        
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
        
        st.session_state.HeatLossPercent = st.number_input("热损估测 (%)", value=float(st.session_state.HeatLossPercent), format="%.2f", step=0.5)

        st.markdown("---")
        # 高级模式开关
        advanced_mode = st.toggle("🛠️ 显示高级配置 (底层煤质/反应器约束)", value=st.session_state.get('advanced_mode', False))
        st.session_state.advanced_mode = advanced_mode

        if advanced_mode:
            # 2. 煤质数据
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

            # 3. 其它边界条件
            with st.expander("🏭 附加管道条件", expanded=True):
                st.session_state.TIN = st.number_input("入口 T (K)", value=float(st.session_state.TIN))
                st.session_state.pt = st.number_input("氧纯度 (%)", value=float(st.session_state.pt))
            
            # 4. 求解策略 (Solver)
            with st.expander("🧮 求解策略设置", expanded=False):
                st.session_state.SolverMethod = st.selectbox("求解算法", ["RGibbs", "Stoic"], 
                    index=0 if st.session_state.SolverMethod=="RGibbs" else 1,
                    help="RGibbs: 全局能量最小化\nStoic: 温差校正反应平衡")
                
                if st.session_state.SolverMethod == "Stoic":
                    st.info("Temperature Approach (K)")
                    sc1, sc2 = st.columns(2)
                    st.session_state.DeltaT_WGS = sc1.number_input("WGS ΔT", value=float(st.session_state.DeltaT_WGS))
                    st.session_state.DeltaT_Meth = sc2.number_input("Meth ΔT", value=float(st.session_state.DeltaT_Meth))

            # 5. 智能校正
            with st.expander("🛠️ 智能热量反算"):
                st.session_state.Target_T = st.number_input("预估目标 T (°C)", value=float(st.session_state.Target_T))
                
                if st.button("开始校正寻找合适热损"):
                    input_data = {k: st.session_state[k] for k in st.session_state.keys() if isinstance(k, (str, int, float))}
                    try:
                        model = GasifierModel(input_data)
                        target_K = st.session_state.Target_T + 273.15
                        with st.spinner("Calibrating..."):
                            loss, _ = model.calculate_heat_loss_for_target_T(target_K)
                            if loss < 0:
                                st.warning(f"自热条件无法达到目标温度。强制热损置0。提议: 增大 O/C")
                                loss = 0.0
                            elif loss < 0.1:
                                 st.warning(f"热损过低: {loss:.2f}%")
                            st.session_state.HeatLossPercent = loss
                            st.success(f"校正成功: 新热损 {loss:.4f}%")
                        st.rerun()
                    except Exception as e:
                        st.error(f"校正失败: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        # 运行按钮放在左侧栏底部
        run_btn = st.button("🚀 开始计算 (Run)", type="primary", use_container_width=True)


    # ==========================================
    # 右侧：结果展示区域
    # ==========================================
    with col_result:
        if run_btn:
            input_data = {k: st.session_state[k] for k in st.session_state.keys() if isinstance(k, (str, int, float))}
            
            try:
                model = GasifierModel(input_data)
                with st.spinner("Solving equilibrium..."):
                    res = model.run_simulation()
                
                st.success("计算完成 (Calculation Complete)")

                # 1. KPIs
                st.subheader("1. 关键性能指标")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("出口温度", f"{res['TOUT_C']:.1f} °C", delta=f"{res['Heat_Err_Pct']:.3f}% Err")
                kpi2.metric("有效气 (CO+H2)", f"{res['Y_CO_dry']+res['Y_H2_dry']:.1f} %")
                kpi3.metric("干气流量", f"{res['Vg_dry']:.0f} Nm³/h")
                kpi4.metric("水气比 (W/G)", f"{res['WGR_Quench']:.3f}")
                
                # 2. 组成
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

                # 3. 激冷
                st.subheader(f"3. 激冷/水洗 (@{st.session_state.T_Scrubber}°C)")
                st.info(f"💧 饱和湿气流量: **{res['Vg_Quench']:.1f} Nm³/h** | 水气比: **{res['WGR_Quench']:.3f}** (mol/mol)")
                
                # 4. 诊断
                with st.expander("🔬 能量与元素平衡诊断"):
                    d1, d2, d3 = st.columns(3)
                    d1.write(f"**热平衡误差:** {res['Heat_Err_Pct']:.4f}%")
                    d2.write(f"**碳平衡误差:** {res['ERR_C']:.4f}%")
                    d3.write(f"**计算 HHV:** {res['HHV']:.2f} kJ/kg")

                # 5. 验证
                if case_name != "Custom (Manual Input)":
                    st.subheader("4. 验证对比 (Validation)")
                    tgt = VALIDATION_CASES[case_name]["expected_output"]
                    val_data = {
                        "Metric": ["Temperature (°C)", "CO (dry%)", "H2 (dry%)", "CO2 (dry%)"],
                        "Model Result": [res['TOUT_C'], res['Y_CO_dry'], res['Y_H2_dry'], res['Y_CO2_dry']],
                        "Paper/Target": [tgt.get('TOUT_C'), tgt.get('YCO'), tgt.get('YH2'), tgt.get('YCO2', 0)],
                    }
                    df_val = pd.DataFrame(val_data)
                    df_val["Diff"] = df_val["Model Result"] - df_val["Paper/Target"]
                    st.dataframe(df_val.round(2), hide_index=True)

            except Exception as e:
                st.error(f"Simulation Failed: {e}")
                st.exception(e)

        else:
            # 默认状态
            st.info("👈 请在左侧配置煤质和工艺参数，然后点击 **开始计算**。")
            st.caption("Gasifier Model v2.0 | Integrated into Chem Portal")

# --- 3. 脚本入口 ---
if __name__ == "__main__":
    st.set_page_config(page_title="EFG Dev", layout="wide")
    run()