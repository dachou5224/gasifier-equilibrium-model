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
from gasifier import GasifierModel
from coal_props import COAL_DATABASE
from validation_cases import VALIDATION_CASES

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
        "Ratio_OC": 0.8,
        "Ratio_SC": 0.08,
        "pt": 99.6,
        "P": 4.0,
        "TIN": 300.0,
        "HeatLossPercent": 1.0,
        "TR": 1500.0,
        "T_Scrubber": 210.0,
        "GasifierType": "Dry Powder",
        "Target_T": 1370.0 # 校正目标温度
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
    
    st.divider()

    # [关键修改] 使用列布局代替 Sidebar
    # 左侧 (1.2): 参数输入区 | 右侧 (2.8): 结果展示区
    col_input, col_result = st.columns([1.2, 2.8], gap="medium")

    # ==========================================
    # 左侧：参数配置区域
    # ==========================================
    with col_input:
        st.info("⚙️ **参数配置面板**")
        
        # 1. 验证工况加载
        with st.expander("📂 加载验证工况", expanded=False):
            case_name = st.selectbox("Select Case", ["Custom (Manual Input)"] + list(VALIDATION_CASES.keys()))
            
            if case_name != "Custom (Manual Input)" and st.button("Load Case Data"):
                data = VALIDATION_CASES[case_name]["inputs"]
                # 加载煤质
                c_data = data["Coal Analysis"]
                if c_data == "SAME_AS_BASE":
                    c_data = VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]["Coal Analysis"]
                for k, v in c_data.items():
                    if k in st.session_state: st.session_state[k] = v
                    
                # 加载工艺
                p_data = data["Process Conditions"]
                for k, v in p_data.items():
                    if k in st.session_state: st.session_state[k] = v
                st.success(f"Loaded!")
                st.rerun()

        # 2. 煤质数据
        with st.expander("🪨 煤质属性", expanded=True):
            selected_db_coal = st.selectbox("数据库", ["None"] + list(COAL_DATABASE.keys()))
            if selected_db_coal != "None":
                if st.button(f"应用 {selected_db_coal}"):
                    db_data = COAL_DATABASE[selected_db_coal]
                    for k, v in db_data.items():
                        if k in st.session_state: st.session_state[k] = v
                    if 'HHV_d' in db_data:
                        st.session_state['HHV_Input'] = db_data['HHV_d'] * 1000.0
                    st.rerun()

            c1, c2 = st.columns(2)
            st.session_state.Cd = c1.number_input("C", value=st.session_state.Cd, format="%.2f")
            st.session_state.Hd = c2.number_input("H", value=st.session_state.Hd, format="%.2f")
            st.session_state.Od = c1.number_input("O", value=st.session_state.Od, format="%.2f")
            st.session_state.Nd = c2.number_input("N", value=st.session_state.Nd, format="%.2f")
            st.session_state.Sd = c1.number_input("S", value=st.session_state.Sd, format="%.2f")
            st.session_state.Ad = c2.number_input("Ash", value=st.session_state.Ad, format="%.2f")
            st.session_state.Mt = st.number_input("Total Moisture (wt%)", value=st.session_state.Mt, format="%.2f")
            # 这里的 Vd 和 FCd 虽然不参与平衡计算，但为了完整性保留
            # st.session_state.Vd = st.number_input("Volatiles", value=st.session_state.Vd) 

            hhv_mode = st.radio("HHV 来源", ["Input", "NICE1 Formula"], 
                                index=st.session_state.HHV_Method, horizontal=True)
            st.session_state.HHV_Method = 0 if hhv_mode == "Input" else 1
            
            if st.session_state.HHV_Method == 0:
                st.session_state.HHV_Input = st.number_input("HHV (kJ/kg, Dry)", value=st.session_state.HHV_Input)

        # 3. 工艺参数
        with st.expander("🏭 工艺条件", expanded=True):
            st.session_state.GasifierType = st.selectbox("炉型", ["Dry Powder", "CWS"], 
                                                         index=0 if st.session_state.GasifierType=="Dry Powder" else 1)
            
            if st.session_state.GasifierType == "Dry Powder":
                st.session_state.FeedRate = st.number_input("干煤投料 (kg/h)", value=st.session_state.FeedRate)
            else:
                st.session_state.FeedRate = st.number_input("煤浆流量 (kg/h)", value=st.session_state.FeedRate)
                st.session_state.SlurryConc = st.number_input("浓度 (wt%)", value=st.session_state.SlurryConc)

            c3, c4 = st.columns(2)
            st.session_state.Ratio_OC = c3.number_input("氧煤比", value=st.session_state.Ratio_OC, format="%.4f")
            st.session_state.Ratio_SC = c4.number_input("汽煤比", value=st.session_state.Ratio_SC, format="%.4f")
            
            st.session_state.P = c3.number_input("压力 (MPa)", value=st.session_state.P)
            st.session_state.TIN = c4.number_input("入口 T (K)", value=st.session_state.TIN)
            st.session_state.pt = st.number_input("氧纯度 (%)", value=st.session_state.pt)
        
        # 4. 智能校正
        with st.expander("🛠️ 智能校正"):
            st.session_state.HeatLossPercent = st.number_input("热损 (%)", value=st.session_state.HeatLossPercent, format="%.4f")
            st.session_state.Target_T = st.number_input("目标出口 T (°C)", value=st.session_state.Target_T)
            
            if st.button("开始校正"):
                input_data = {k: st.session_state[k] for k in st.session_state.keys() if isinstance(k, (str, int, float))}
                try:
                    model = GasifierModel(input_data)
                    target_K = st.session_state.Target_T + 273.15
                    with st.spinner("Calibrating..."):
                        loss, _ = model.calculate_heat_loss_for_target_T(target_K)
                        if loss < 0.1:
                            st.warning(f"热损过低 ({loss:.2f}%)，自动调整氧煤比")
                            fixed_loss = 1.0
                            new_ratio = model.calculate_oxygen_ratio_for_target_T(target_K, fixed_loss_percent=fixed_loss)
                            st.session_state.HeatLossPercent = fixed_loss
                            st.session_state.Ratio_OC = new_ratio
                            st.success(f"新氧煤比: {new_ratio:.4f}")
                        else:
                            st.session_state.HeatLossPercent = loss
                            st.success(f"新热损: {loss:.4f}%")
                    st.rerun()
                except Exception as e:
                    st.error(f"校正失败: {e}")

        st.markdown("---")
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