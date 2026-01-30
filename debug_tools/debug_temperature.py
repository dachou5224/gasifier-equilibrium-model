"""
温度异常诊断工具
目标: 找出为什么预测温度远低于期望 (548°C vs 1370°C)
"""

import sys
import os

# Add src to path (assuming script is in debug_tools/, so ../src)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from gasifier.thermo_data import get_enthalpy_molar, get_gibbs_free_energy
import numpy as np

def debug_temperature_calculation():
    """逐步诊断温度计算过程"""
    
    print("="*70)
    print("🔍 温度异常诊断 - Paper_Case_6 (Calibrated)")
    print("="*70)
    
    # 使用失败的案例输入
    inputs = {
        "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
        "Ad": 7.35, "Vd": 31.24, "FCd": 61.41, 
        "Mt": 4.53,
        "HHV_Input": 29800.0,
        "FeedRate": 41670.0,
        "SlurryConc": 60.0,
        "Ratio_OC": 0.86,
        "Ratio_SC": 0.08,
        "pt": 99.6,
        "P": 4.08,
        "TIN": 300.0,
        "HeatLossPercent": 2.85,
        "GasifierType": "Dry Powder"
    }
    
    model = GasifierModel(inputs)
    model._preprocess_inputs()
    
    print("\n📋 Step 1: 检查输入预处理")
    print("-"*70)
    print(f"煤干基流量 (Gc_dry): {model.Gc_dry:.2f} kg/h")
    print(f"煤HHV: {model.HHV_coal:.0f} kJ/kg")
    print(f"煤生成焓: {model.H_coal_form:.0f} kJ/kg")
    print(f"热损失: {model.abs_heat_loss:.0f} J/h = {model.abs_heat_loss/model.Gc_dry/model.HHV_coal*100:.2f}%")
    print(f"氧气摩尔数: {model.flow_in['O2_mol']:.2f} mol/h")
    print(f"蒸汽质量: {model.m_steam_gas:.2f} kg/h")
    
    print(f"\n原子输入 [C, H, O, N, S]:")
    print(f"  {model.atom_input}")
    
    # 检查能量平衡函数在不同温度下的值
    print("\n📋 Step 2: 扫描能量平衡函数")
    print("-"*70)
    print(f"{'温度(K)':<12} {'温度(°C)':<12} {'能量差(J)':<20} {'说明':<30}")
    print("-"*70)
    
    test_temps = [500, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2500, 3000, 3500]
    balances = []
    
    for T in test_temps:
        balance = model._calculate_enthalpy_balance(T)
        balances.append(balance)
        
        T_C = T - 273.15
        sign = "正(H_in > H_out)" if balance > 0 else "负(H_out > H_in)"
        
        print(f"{T:<12.0f} {T_C:<12.1f} {balance:<20.2e} {sign:<30}")
    
    # 检查是否有零点
    balances_array = np.array(balances)
    sign_changes = np.where(np.diff(np.sign(balances_array)))[0]
    
    print(f"\n🔍 零点分析:")
    if len(sign_changes) > 0:
        print(f"  发现 {len(sign_changes)} 个零点 (符号变化)")
        for i in sign_changes:
            T1, T2 = test_temps[i], test_temps[i+1]
            print(f"    零点区间: {T1}K ({T1-273:.0f}°C) ~ {T2}K ({T2-273:.0f}°C)")
    else:
        print(f"  ❌ 在测试范围内未找到零点!")
        print(f"  能量平衡始终为: {'正值' if all(b > 0 for b in balances) else '负值'}")
        
        if all(b > 0 for b in balances):
            print(f"  → 说明 H_in 始终大于 H_out")
            print(f"  → 可能原因: 热损失过大,或煤生成焓计算错误")
        else:
            print(f"  → 说明 H_out 始终大于 H_in")
            print(f"  → 可能原因: 煤生成焓过高,或氧气过少")
    
    # 详细检查某个温度点的能量组成
    print("\n📋 Step 3: 详细分析 T=1400°C 的能量平衡")
    print("-"*70)
    
    T_test = 1673.15  # 1400°C
    moles = model.solve_equilibrium_at_T(T_test)
    
    print(f"\n气相组成 (mol/h):")
    for i, species in enumerate(model.species_list):
        print(f"  {species:<6}: {moles[i]:>12.2f} mol/h")
    
    # 输出焓详细计算
    print(f"\n输出焓计算 (T={T_test}K = {T_test-273.15:.0f}°C):")
    H_gas_out = 0.0
    for i, species in enumerate(model.species_list):
        H_species = get_enthalpy_molar(species, T_test)
        H_total = moles[i] * H_species
        H_gas_out += H_total
        print(f"  {species:<6}: {moles[i]:>10.2f} mol × {H_species:>12.0f} J/mol = {H_total:>15.2e} J")
    
    print(f"\n  气相总焓: {H_gas_out:>15.2e} J/h")
    print(f"  热损失:   {model.abs_heat_loss:>15.2e} J/h")
    print(f"  输出总计: {H_gas_out + model.abs_heat_loss:>15.2e} J/h")
    
    # 输入焓计算
    print(f"\n输入焓计算:")
    
    # 煤
    T_coal_in = inputs.get('T_Coal_In', 298.15)
    Cp_coal = 1.2
    H_coal_sensible = model.Gc_dry * Cp_coal * (T_coal_in - 298.15)
    H_coal_total = model.Gc_dry * model.H_coal_form + H_coal_sensible
    print(f"  煤生成焓:   {model.Gc_dry * model.H_coal_form:>15.2e} J/h")
    print(f"  煤显热:     {H_coal_sensible:>15.2e} J/h")
    print(f"  煤总焓:     {H_coal_total:>15.2e} J/h")
    
    # 气体
    T_gas_in = inputs['TIN']
    H_O2 = model.flow_in['O2_mol'] * get_enthalpy_molar('O2', T_gas_in)
    H_N2 = model.flow_in['N2_ox_mol'] * get_enthalpy_molar('N2', T_gas_in)
    H_steam = (model.m_steam_gas/18.015) * get_enthalpy_molar('H2O', T_gas_in)
    print(f"  O2焓:       {H_O2:>15.2e} J/h")
    print(f"  N2焓:       {H_N2:>15.2e} J/h")
    print(f"  蒸汽焓:     {H_steam:>15.2e} J/h")
    
    # 液态水
    T_water_in = inputs.get('T_Slurry_In', 298.15)
    H_water_liq = (model.m_water_liq/18.015) * (-285830.0 + 75.3 * (T_water_in - 298.15))
    print(f"  液态水焓:   {H_water_liq:>15.2e} J/h")
    
    H_in_total = H_coal_total + H_O2 + H_N2 + H_steam + H_water_liq
    print(f"  输入总计:   {H_in_total:>15.2e} J/h")
    
    balance_1400 = H_in_total - (H_gas_out + model.abs_heat_loss)
    print(f"\n  能量差:     {balance_1400:>15.2e} J/h")
    print(f"  能量差占比: {balance_1400/H_in_total*100:>14.2f} %")
    
    # 检查煤生成焓是否合理
    print("\n📋 Step 4: 验证煤生成焓计算")
    print("-"*70)
    
    # 手动计算验证
    # 手动计算验证
    MW_C, MW_H, MW_S = 12.011, 1.008, 32.065
    n_C = (inputs['Cd']/100.0) / MW_C * 1000.0 # mol/kg
    n_H = (inputs['Hd']/100.0) / MW_H * 1000.0 # mol/kg
    n_S = (inputs['Sd']/100.0) / MW_S * 1000.0 # mol/kg
    
    Hf_CO2 = -393510.0
    Hf_H2O_L = -285830.0
    Hf_SO2 = -296830.0
    
    # H = mol/kg * J/mol = J/kg
    H_combustion = (n_C * Hf_CO2) + (n_H * 0.5 * Hf_H2O_L) + (n_S * Hf_SO2)
    H_formation_calc = H_combustion + model.HHV_coal
    
    print(f"完全燃烧产物焓: {H_combustion:.2f} J/kg")
    print(f"高位热值:       {model.HHV_coal:.2f} J/kg")
    print(f"煤生成焓(计算): {H_formation_calc:.2f} J/kg")
    print(f"煤生成焓(模型): {model.H_coal_form:.2f} J/kg")
    print(f"差值:           {abs(H_formation_calc - model.H_coal_form):.2f} J/kg")
    
    if abs(H_formation_calc - model.H_coal_form) > 100000: # 100 kJ margin
        print(f"  ⚠️ 警告: 煤生成焓计算可能有误!")
    else:
        print(f"  ✅ 煤生成焓计算正确")
    
    print("\n" + "="*70)
    print("🎯 诊断结论:")
    print("="*70)
    
    # 给出诊断建议
    if len(sign_changes) == 0:
        print("❌ 主要问题: 能量平衡函数在整个温度范围无零点")
        print("\n可能原因:")
        print("  1. 煤生成焓计算错误 (符号或数值)")
        print("  2. 热损失设置过大")
        print("  3. HHV数值错误")
        print("  4. 氧气流量计算错误")
        print(f"\n  当前Balance范围: Max={max(balances):.2e}, Min={min(balances):.2e}")
        
    else:
        print("✅ 能量平衡函数有零点,但可能收敛到错误的解")
        print("\n可能原因:")
        print("  1. brentq 搜索范围问题")
        print("  2. 多个零点导致收敛到局部解")
        print("  3. 数值精度问题")


def check_hhv_units():
    """检查HHV单位是否一致"""
    print("\n" + "="*70)
    print("🔍 检查HHV单位一致性")
    print("="*70)
    
    from gasifier.coal_props import COAL_DATABASE
    
    print("\n数据库中的HHV值 (J/kg):")
    for coal_name, props in COAL_DATABASE.items():
        # DATABASE uses kJ/kg? No, I updated it to use J/kg?
        # Check coal_props: I updated calculate_coal_thermo. 
        # But COAL_DATABASE values? "HHV_d": 30720.0 (Wait, in coal_props I saw 30720).
        # original comment said "kJ/kg". 
        # But 30720 kJ/kg is 30 MJ/kg. Correct.
        # But calculate_coal_thermo assumes inputs < 200 is MJ.
        # 30720 > 200. So treated as kJ/kg. Converter multiplies by 1000.
        # So it becomes 3e7 J/kg. Correct.
        hhv_db = props.get('HHV_d', 0)
        print(f"  {coal_name:<25}: {hhv_db:>8.2f} kJ/kg (Raw in DB)")
    
    print("\nvalidation_cases中的HHV:")
    print(f"  Paper_Case_6: {29800.0:>8.2f} (单位不明)")
    
    print("\n⚠️ 警告:")
    print("  数据库使用: MJ/kg")
    print("  validation使用: 可能是 kJ/kg")
    print("  如果单位不匹配,会导致:")
    print("    - 生成焓计算错误 (差1000倍)")
    print("    - 能量平衡失效")
    print("    - 温度严重偏离")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║          温度异常诊断工具                                    ║
    ║          目标: 找出为什么温度只有548°C而不是1370°C          ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    debug_temperature_calculation()
    check_hhv_units()
    
    print("\n💡 下一步:")
    print("  1. 根据诊断结果修正代码")
    print("  2. 确认HHV单位 (kJ/kg vs MJ/kg)")
    print("  3. 检查煤生成焓公式的符号")
    print("  4. 重新运行验证测试\n")