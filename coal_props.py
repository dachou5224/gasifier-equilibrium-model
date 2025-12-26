# coal_props.py
import numpy as np

# =======================================================
# 内置煤质数据库 (更新版)
# 数据来源: image_77fce4.png
# 增加字段: HHV_d (干燥基高位热值, MJ/kg -> 存储时建议转为 float)
# =======================================================
COAL_DATABASE = {
    "ShenYou 1 (神优1)": {
        "Mt": 14.3, "Ad": 7.22, "Vd": 34.96, "FCd": 57.82,
        "Cd": 75.83, "Hd": 4.58, "Od": 10.89, "Nd": 1.19, "Sd": 0.29,
        "HHV_d": 30.72 # MJ/kg
    },
    "ShenYou 2 (神优2)": {
        "Mt": 14.2, "Ad": 7.62, "Vd": 31.60, "FCd": 60.78,
        "Cd": 75.68, "Hd": 4.12, "Od": 11.12, "Nd": 1.04, "Sd": 0.44,
        "HHV_d": 29.74
    },
    "ShenYou 3 (神优3)": {
        "Mt": 16.2, "Ad": 9.80, "Vd": 31.92, "FCd": 58.28,
        "Cd": 73.33, "Hd": 3.92, "Od": 12.66, "Nd": 0.95, "Sd": 0.25,
        "HHV_d": 28.62
    },
    "TeDiHui (特低灰)": {
        "Mt": 17.1, "Ad": 5.68, "Vd": 35.2, "FCd": 59.12,
        "Cd": 74.3, "Hd": 4.12, "Od": 14.7, "Nd": 0.87, "Sd": 0.21,
        "HHV_d": 28.01 # 对应图片中特低灰的 Qgr,v,d
    }
}

def calculate_coal_thermo(inputs, use_formula=False):
    """
    计算煤的热力学性质
    
    参数:
    inputs: 包含煤质数据的字典
    use_formula: Boolean. 
                 True = 强制使用 NICE1 公式计算 HHV
                 False = 优先使用 inputs['HHV_Input'] (即数据库值/手动输入值)
    """
    
    # 1. 确定 HHV (kJ/kg)
    hhv_kj_kg = 0.0
    
    if not use_formula and 'HHV_Input' in inputs and inputs['HHV_Input'] > 0:
        # --- 方法 A: 直接使用输入值/数据库值 ---
        hhv_kj_kg = inputs['HHV_Input']
    else:
        # --- 方法 B: 使用 NICE1 公式计算 ---
        # Q_gr,d = 0.2722*Vd + 0.3564*FCd (MJ/kg)
        Vd = inputs.get('Vd', 30.0)
        FCd = inputs.get('FCd', 100.0 - inputs.get('Ad', 0) - Vd)
        
        hhv_kj_kg = (0.2722 * Vd + 0.3564 * FCd) * 1000.0
    
    # 2. 计算生成焓 (SIMTECH2 Logic)
    # Hf_coal = H_products + HHV
    
    Hf_CO2 = -393510.0
    Hf_H2O_L = -285830.0 
    Hf_SO2 = -296830.0
    
    MW_C = 12.011
    MW_H = 1.008
    MW_S = 32.065
    
    n_C = (inputs['Cd'] / 100.0) / MW_C
    n_H = (inputs['Hd'] / 100.0) / MW_H
    n_S = (inputs['Sd'] / 100.0) / MW_S
    
    H_combustion_products = (n_C * Hf_CO2) + (n_H * 0.5 * Hf_H2O_L) + (n_S * Hf_SO2)
    
    # 无论 HHV 来源如何，生成焓计算公式结构不变，只是数值受 HHV 影响
    h_formation_kj_kg = H_combustion_products + hhv_kj_kg
    
    return {
        'HHV': hhv_kj_kg,
        'H_formation': h_formation_kj_kg,
        'Method': 'Formula (NICE1)' if use_formula else 'Database/Input'
    }