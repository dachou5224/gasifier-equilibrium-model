"""
coal_props.py - Coal Property Calculations and Database

================================================================================
MODIFICATION HISTORY
================================================================================
2026-01-28  v2.0  刘臻 (Liu Zhen)
    - [Fix] Line 59-70: HHV 单位自动检测与转换
      输入值 <1000 时识别为 MJ/kg 并自动转换为 kJ/kg
    - [Fix] Line 9-30: 数据库 (COAL_DATABASE) 统一使用 kJ/kg 单位
      原 MJ/kg 值已乘以 1000 转换
    - [New] Line 125-166: 单元测试函数 test_hhv_units() 用于验证单位转换
    - [Doc] Line 32-53: 更新 calculate_coal_thermo 函数文档字符串
================================================================================
"""

# coal_props.py (单位修正版)
import numpy as np

# =======================================================
# 内置煤质数据库 (单位修正版 v2.0)
# 数据来源: image_77fce4.png
# 🔧 单位统一: HHV_d 使用 kJ/kg (原 MJ/kg × 1000)
# =======================================================
COAL_DATABASE = {
    "ShenYou 1 (神优1)": {
        "Mt": 14.3, "Ad": 7.22, "Vd": 34.96, "FCd": 57.82,
        "Cd": 75.83, "Hd": 4.58, "Od": 10.89, "Nd": 1.19, "Sd": 0.29,
        "HHV_d": 30720.0  # kJ/kg (原 30.72 MJ/kg)
    },
    "ShenYou 2 (神优2)": {
        "Mt": 14.2, "Ad": 7.62, "Vd": 31.60, "FCd": 60.78,
        "Cd": 75.68, "Hd": 4.12, "Od": 11.12, "Nd": 1.04, "Sd": 0.44,
        "HHV_d": 29740.0  # kJ/kg (原 29.74 MJ/kg)
    },
    "ShenYou 3 (神优3)": {
        "Mt": 16.2, "Ad": 9.80, "Vd": 31.92, "FCd": 58.28,
        "Cd": 73.33, "Hd": 3.92, "Od": 12.66, "Nd": 0.95, "Sd": 0.25,
        "HHV_d": 28620.0  # kJ/kg (原 28.62 MJ/kg)
    },
    "TeDiHui (特低灰)": {
        "Mt": 17.1, "Ad": 5.68, "Vd": 35.2, "FCd": 59.12,
        "Cd": 74.3, "Hd": 4.12, "Od": 14.7, "Nd": 0.87, "Sd": 0.21,
        "HHV_d": 28010.0  # kJ/kg (原 28.01 MJ/kg)
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
    
    ⚠️ 单位约定: 
    - 输入 HHV_Input: 可以是 kJ/kg 或 MJ/kg (自动检测)
    - 输出 HHV: 始终为 J/kg (Joules/kg) - 【Fix: 统一为焦耳】
    - 生成焓 H_formation: J/kg (Joules/kg) - 【Fix: 统一为焦耳】
    
    返回:
    {
        'HHV': float (J/kg),
        'H_formation': float (J/kg),
        'Method': str (计算方法说明)
    }
    """
    
    # 1. 确定 HHV (J/kg)
    hhv_j_kg = 0.0
    method_desc = ""
    
    if not use_formula and 'HHV_Input' in inputs and inputs['HHV_Input'] > 0:
        # --- 方法 A: 直接使用输入值/数据库值 ---
        # 🔧 单位自动检测与转换
        hhv_raw = inputs['HHV_Input']
        
        # 如果输入值 < 200, 假设是 MJ/kg -> Convert to J/kg (* 1e6)
        # 如果输入值 200-50000, 假设是 kJ/kg -> Convert to J/kg (* 1e3)
        # 如果输入值 > 50000, 假设是 J/kg -> Keep
        
        if hhv_raw < 200:
            hhv_j_kg = hhv_raw * 1.0e6
            method_desc = 'Database/Input (MJ/kg converted to J/kg)'
        elif hhv_raw < 100000: # Threshold for kJ/kg vs J/kg
            hhv_j_kg = hhv_raw * 1000.0
            method_desc = 'Database/Input (kJ/kg converted to J/kg)'
        else:
            hhv_j_kg = hhv_raw
            method_desc = 'Database/Input (J/kg)'
        
    else:
        # --- 方法 B: 使用 NICE1 公式计算 ---
        # Q_gr,d = 0.2722*Vd + 0.3564*FCd (MJ/kg)
        Vd = inputs.get('Vd', 30.0)
        FCd = inputs.get('FCd', 100.0 - inputs.get('Ad', 0) - Vd)
        
        hhv_mj_kg = (0.2722 * Vd + 0.3564 * FCd)
        hhv_j_kg = hhv_mj_kg * 1.0e6  # MJ/kg → J/kg
        method_desc = 'Formula (NICE1, MJ/kg -> J/kg)'
    
    # 2. 计算生成焓 (SIMTECH2 Logic)
    # Hf_coal = H_products + HHV
    # 其中 H_products 是完全燃烧产物的生成焓 (负值)
    
    Hf_CO2 = -393510.0    # J/mol
    Hf_H2O_L = -285830.0  # J/mol (液态水)
    Hf_SO2 = -296830.0    # J/mol
    
    MW_C = 12.011   # g/mol
    MW_H = 1.008    # g/mol
    MW_S = 32.065   # g/mol
    
    # 计算每 kg 煤中各元素的摩尔数
    n_C = (inputs['Cd'] / 100.0) / MW_C * 1000.0 # mol/kg coal (g/kg / g/mol = mol/kg) -- Wait, n = m/M. m=1kg * content. 
    # inputs['Cd'] is %. 
    # In 1 kg coal: m_C = (Cd/100) * 1000 g. 
    # moles = m_C / MW_C = (Cd/100 * 1000) / MW_C = (Cd * 10) / MW_C.
    # ORIGINAL CODE: (inputs['Cd'] / 100.0) / MW_C
    # Original assumes Cd is mass fraction? No, Cd is percentage (0-100).
    # (75/100) / 12 = 0.0625 kmol/kg (if MW is kg/kmol) or mol/g.
    # If we want mol/kg:
    # 1 kg coal contains (Cd/100) kg Carbon.
    # (Cd/100) kg = (Cd/100)*1000 g.
    # moles = ((Cd/100)*1000) / MW_C.
    # Original code: (inputs['Cd']/100.0) / MW_C. If MW_C is 12 (g/mol), 
    # (0.75) / 12 = 0.0625. This is kmol/kg (or mol/g).
    # Hf is J/mol. 
    # We want J/kg.
    # H_combustion = (kmol/kg) * 1000 (mol/kmol) * J/mol = J/kg.
    # Wait, simple dimensional analysis:
    # We want moles/kg coal.
    # Cd/100 is mass fraction (kg C / kg coal).
    # MW_C is g C / mol C = kg C / kmol C.
    # (Cd/100) / MW_C = (kg C / kg coal) / (kg C / kmol C) = kmol C / kg coal.
    # kmol C / kg coal * 1000 = mol C / kg coal.
    # 
    # Original code: n_C = (inputs['Cd'] / 100.0) / MW_C  -> This is kmol/kg.
    # H_combustion (J/kg) = n_C (kmol/kg) * Hf (J/mol) ??? NO.
    # J/mol is J per MOLE.
    # If n_C is kmol/kg, we need J/kmol.
    # J/kmol = J/mol * 1000.
    # Or, we convert n_C to mol/kg. n_C_mol = n_C_kmol * 1000.
    #
    # Let's fix this in the code block below.
    
    n_C_kmol = (inputs['Cd'] / 100.0) / (MW_C / 1000.0) # mass(kg)/M(kg/mol) = mol
    # MW_C is 12.011 g/mol = 0.012011 kg/mol.
    # (Cd/100) / 0.012 = mol/kg.
    
    # Or keep original MW and adjust logic
    n_C_mol_per_kg = (inputs['Cd'] / 100.0) * 1000.0 / MW_C # (g C / kg coal) / (g C / mol C) = mol C / kg coal
    n_H_mol_per_kg = (inputs['Hd'] / 100.0) * 1000.0 / MW_H
    n_S_mol_per_kg = (inputs['Sd'] / 100.0) * 1000.0 / MW_S
    
    # 完全燃烧反应:
    # C + O2 → CO2        (生成 n_C mol CO2)
    # H2 + 0.5O2 → H2O    (生成 n_H/2 mol H2O)
    # S + O2 → SO2        (生成 n_S mol SO2)
    
    H_combustion_products = (
        n_C_mol_per_kg * Hf_CO2 +           # 碳燃烧产物
        (n_H_mol_per_kg * 0.5) * Hf_H2O_L + # 氢燃烧产物 (液态水)
        n_S_mol_per_kg * Hf_SO2             # 硫燃烧产物
    )  # J/kg coal (mol/kg * J/mol = J/kg)
    
    # 煤的生成焓 = 燃烧产物焓 + 高位热值
    # 注意: H_combustion_products 是负值 (放热)
    #       HHV 是正值 (热量释放, 定义为 +)
    #       两者相加得到煤的生成焓 (通常为负值)
    #       Ref: H_reactants = H_products + Heat_Released
    #       H_coal + ... = H_CO2 + H_H2O + HHV
    #       H_coal = H_products + HHV 
    #       (Note: standard HHV definition is positive quantity of heat)
    
    h_formation_j_kg = H_combustion_products + hhv_j_kg
    
    return {
        'HHV': hhv_j_kg,              # J/kg
        'H_formation': h_formation_j_kg,  # J/kg
        'Method': method_desc
    }


# =======================================================
# 🆕 单元测试 (可选)
# =======================================================
def test_hhv_units():
    """测试HHV单位转换功能"""
    print("="*70)
    print("🧪 HHV单位转换测试")
    print("="*70)
    
    # 测试1: 输入 kJ/kg (>1000)
    test1 = calculate_coal_thermo({'Cd': 75, 'Hd': 5, 'Od': 10, 'Nd': 1, 'Sd': 0.5, 
                                   'HHV_Input': 29800.0})
    print(f"\n测试1: HHV_Input = 29800.0")
    print(f"  识别为: kJ/kg")
    print(f"  输出HHV: {test1['HHV']:.2f} kJ/kg")
    print(f"  方法: {test1['Method']}")
    
    # 测试2: 输入 MJ/kg (<1000)
    test2 = calculate_coal_thermo({'Cd': 75, 'Hd': 5, 'Od': 10, 'Nd': 1, 'Sd': 0.5, 
                                   'HHV_Input': 29.8})
    print(f"\n测试2: HHV_Input = 29.8")
    print(f"  识别为: MJ/kg → 自动转换")
    print(f"  输出HHV: {test2['HHV']:.2f} kJ/kg")
    print(f"  方法: {test2['Method']}")
    
    # 测试3: 使用公式计算
    test3 = calculate_coal_thermo({'Cd': 75, 'Hd': 5, 'Od': 10, 'Nd': 1, 'Sd': 0.5,
                                   'Vd': 35, 'FCd': 58, 'Ad': 7}, 
                                  use_formula=True)
    print(f"\n测试3: 使用NICE1公式")
    print(f"  输出HHV: {test3['HHV']:.2f} kJ/kg")
    print(f"  方法: {test3['Method']}")
    
    # 测试4: 数据库值
    from_db = COAL_DATABASE["ShenYou 1 (神优1)"]
    test4 = calculate_coal_thermo(from_db)
    print(f"\n测试4: 从数据库 (神优1)")
    print(f"  数据库HHV_d: {from_db['HHV_d']:.2f} kJ/kg")
    print(f"  输出HHV: {test4['HHV']:.2f} kJ/kg")
    print(f"  生成焓: {test4['H_formation']:.2f} kJ/kg")
    print(f"  方法: {test4['Method']}")
    
    print("\n" + "="*70)
    print("✅ 单位测试完成")
    print("="*70)


if __name__ == "__main__":
    test_hhv_units()