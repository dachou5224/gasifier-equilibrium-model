import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from gasifier import GasifierModel
from coal_props import COAL_DATABASE
from validation_cases import VALIDATION_CASES

# 页面配置
st.set_page_config(
    page_title="EFG Simulation Model",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 辅助函数：初始化 Session State ---
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
        "TIN": 500.0,
        "HeatLossPercent": 1.0,
        "TR": 1500.0,
        "T_Scrubber": 210.0,
        "GasifierType": "Dry Powder",
        "Target_T": 1370.0 # 校正目标温度
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()

# --- 侧边栏：输入区域 ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # --- 1. 验证工况加载 ---
    st.subheader("1. Load Validation Case")
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
        st.success(f"Loaded {case_name}")
        st.rerun()

    st.divider()

    # --- 2. 煤质数据 ---
    st.subheader("2. Coal Properties")
    
    # 数据库选择
    selected_db_coal = st.selectbox("Load form Database", ["None"] + list(COAL_DATABASE.keys()))
    if selected_db_coal != "None":
        db_data = COAL_DATABASE[selected_db_coal]
        if st.button(f"Apply {selected_db_coal}"):
            for k, v in db_data.items():
                if k in st.session_state: st.session_state[k] = v
            if 'HHV_d' in db_data:
                st.session_state['HHV_Input'] = db_data['HHV_d'] * 1000.0
            st.rerun()

    # 煤质输入表单
    with st.expander("Edit Coal Composition (Dry Basis wt%)", expanded=False):
        c1, c2 = st.columns(2)
        st.session_state.Cd = c1.number_input("C", value=st.session_state.Cd, format="%.2f")
        st.session_state.Hd = c2.number_input("H", value=st.session_state.Hd, format="%.2f")
        st.session_state.Od = c1.number_input("O", value=st.session_state.Od, format="%.2f")
        st.session_state.Nd = c2.number_input("N", value=st.session_state.Nd, format="%.2f")
        st.session_state.Sd = c1.number_input("S", value=st.session_state.Sd, format="%.2f")
        st.session_state.Ad = c2.number_input("Ash", value=st.session_state.Ad, format="%.2f")
        st.session_state.Mt = st.number_input("Total Moisture (wt%)", value=st.session_state.Mt, format="%.2f")
        st.session_state.Vd = st.number_input("Volatiles (Vd)", value=st.session_state.Vd, format="%.2f")
        st.session_state.FCd = st.number_input("Fixed Carbon (FCd)", value=st.session_state.FCd, format="%.2f")

    # HHV 设置
    hhv_mode = st.radio("HHV Source", ["Input/Database", "Formula (NICE1)"], 
                        index=st.session_state.HHV_Method, horizontal=True)
    st.session_state.HHV_Method = 0 if hhv_mode == "Input/Database" else 1
    
    if st.session_state.HHV_Method == 0:
        st.session_state.HHV_Input = st.number_input("HHV (kJ/kg, Dry)", value=st.session_state.HHV_Input)

    st.divider()

    # --- 3. 工艺参数 ---
    st.subheader("3. Process Conditions")
    
    st.session_state.GasifierType = st.selectbox("Gasifier Type", ["Dry Powder", "CWS"], 
                                                 index=0 if st.session_state.GasifierType=="Dry Powder" else 1)
    
    if st.session_state.GasifierType == "Dry Powder":
        st.session_state.FeedRate = st.number_input("Coal Feed Rate (kg/h)", value=st.session_state.FeedRate)
    else:
        st.session_state.FeedRate = st.number_input("Slurry Feed Rate (kg/h)", value=st.session_state.FeedRate)
        st.session_state.SlurryConc = st.number_input("Slurry Concentration (wt%)", value=st.session_state.SlurryConc)

    c3, c4 = st.columns(2)
    st.session_state.Ratio_OC = c3.number_input("O2/Coal Ratio", value=st.session_state.Ratio_OC, format="%.4f")
    st.session_state.Ratio_SC = c4.number_input("Steam/Coal Ratio", value=st.session_state.Ratio_SC, format="%.4f")
    
    st.session_state.P = c3.number_input("Pressure (MPa)", value=st.session_state.P)
    st.session_state.TIN = c4.number_input("Inlet Temp (K)", value=st.session_state.TIN)
    st.session_state.pt = st.number_input("O2 Purity (%)", value=st.session_state.pt)
    
    st.divider()
    
    # --- 4. 智能校正 ---
    st.subheader("🛠️ Smart Calibration")
    st.session_state.HeatLossPercent = st.number_input("Heat Loss (% HHV)", value=st.session_state.HeatLossPercent, format="%.4f")
    
    st.session_state.Target_T = st.number_input("Target Outlet T (°C)", value=st.session_state.Target_T)
    
    if st.button("Auto-Calibrate"):
        input_data = {k: st.session_state[k] for k in st.session_state.keys() if isinstance(k, str)}
        try:
            model = GasifierModel(input_data)
            target_K = st.session_state.Target_T + 273.15
            
            with st.spinner("Calibrating..."):
                # 策略1: 反算热损
                loss, _ = model.calculate_heat_loss_for_target_T(target_K)
                
                if loss < 0.1:
                    # 策略2: 反算氧煤比
                    st.warning(f"Calculated Heat Loss ({loss:.2f}%) is unrealistic. Switching to O2 adjustment.")
                    fixed_loss = 1.0
                    new_ratio = model.calculate_oxygen_ratio_for_target_T(target_K, fixed_loss_percent=fixed_loss)
                    
                    st.session_state.HeatLossPercent = fixed_loss
                    st.session_state.Ratio_OC = new_ratio
                    st.success(f"Calibrated! Adjusted O/C Ratio to {new_ratio:.4f}")
                else:
                    st.session_state.HeatLossPercent = loss
                    st.success(f"Calibrated! Adjusted Heat Loss to {loss:.4f}%")
            st.rerun()
            
        except Exception as e:
            st.error(f"Calibration Failed: {e}")

# --- 主界面：运行与结果 ---
st.title("🏭 Entrained Flow Gasifier Model")
st.markdown("Thermodynamic equilibrium simulation based on Gibbs Free Energy Minimization.")

if st.button("Run Simulation", type="primary", use_container_width=True):
    # 构建输入字典
    input_data = {k: st.session_state[k] for k in st.session_state.keys() if isinstance(k, str)}
    
    try:
        model = GasifierModel(input_data)
        with st.spinner("Solving equilibrium..."):
            res = model.run_simulation()
        
        # --- 结果展示 ---
        
        # 1. 关键指标 (KPIs)
        st.subheader("1. Key Performance Indicators")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Outlet Temp", f"{res['TOUT_C']:.2f} °C")
        kpi2.metric("Syngas (Dry)", f"{res['Vg_dry']:.1f} Nm³/h")
        kpi3.metric("Syngas (Wet)", f"{res['Vg_wet']:.1f} Nm³/h")
        kpi4.metric("H₂O Content", f"{res['Y_H2O_wet']:.2f} %")
        
        # 2. 激冷/水洗数据
        st.subheader(f"2. Quench / Scrubber Outlet (@{st.session_state.T_Scrubber}°C)")
        q1, q2 = st.columns(2)
        q1.metric("Total Wet Flow (Saturated)", f"{res['Vg_Quench']:.1f} Nm³/h", delta_color="off")
        q2.metric("Water/Gas Ratio", f"{res['WGR_Quench']:.4f} mol/mol")
        
        # 3. 气体组成 (Composition)
        st.subheader("3. Syngas Composition")
        
        comp_data = {
            "Component": ["CO", "H2", "CO2", "CH4", "N2", "H2O"],
            "Dry Basis (vol%)": [
                res['Y_CO_dry'], res['Y_H2_dry'], res['Y_CO2_dry'], 
                res['Y_CH4_dry'], res['Y_N2_dry'], 0.0
            ],
            "Wet Basis (vol%)": [
                res['Y_CO_wet'], res['Y_H2_wet'], res['Y_CO2_wet'], 
                res['Y_CH4_wet'], res['Y_N2_wet'], res['Y_H2O_wet']
            ]
        }
        df_comp = pd.DataFrame(comp_data)
        
        c_table, c_chart = st.columns([1, 1])
        with c_table:
            # [FIXED] 移除了 .style.format 以避免 Pandas 版本兼容问题
            # 直接使用 round(2) 保留两位小数
            st.dataframe(df_comp.round(2), hide_index=True, use_container_width=True)
            
        with c_chart:
            # 使用 Plotly 绘制饼图
            fig = go.Figure(data=[go.Pie(labels=df_comp["Component"], 
                                         values=df_comp["Dry Basis (vol%)"], 
                                         hole=.4,
                                         title="Dry Composition")])
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250)
            st.plotly_chart(fig, use_container_width=True)

        # 4. 诊断信息 (Diagnostics)
        with st.expander("🔬 Model Diagnostics & Energy Balance"):
            d1, d2, d3 = st.columns(3)
            d1.write(f"**Heat Balance Error:** {res['Heat_Err_Pct']:.4f}%")
            d2.write(f"**Carbon Balance Error:** {res['ERR_C']:.4f}%")
            d3.write(f"**Calculated HHV:** {res['HHV']:.2f} kJ/kg")
            st.write(f"**HHV Method Used:** {res['Method']}")
            
        # 5. 验证对比 (如果选择了 Case)
        if case_name != "Custom (Manual Input)":
            st.subheader("4. Validation Benchmark")
            tgt = VALIDATION_CASES[case_name]["expected_output"]
            
            val_data = {
                "Metric": ["Temperature (°C)", "CO (dry%)", "H2 (dry%)", "CO2 (dry%)"],
                "Model Result": [res['TOUT_C'], res['Y_CO_dry'], res['Y_H2_dry'], res['Y_CO2_dry']],
                "Paper/Target": [tgt.get('TOUT_C'), tgt.get('YCO'), tgt.get('YH2'), tgt.get('YCO2', 0)],
            }
            df_val = pd.DataFrame(val_data)
            df_val["Diff"] = df_val["Model Result"] - df_val["Paper/Target"]
            
            # [FIXED] 移除了 .style.format
            st.dataframe(df_val.round(2), hide_index=True)

    except Exception as e:
        st.error(f"Simulation Failed: {e}")
        st.exception(e)

else:
    st.info("👈 Configure parameters in the sidebar and click 'Run Simulation'")