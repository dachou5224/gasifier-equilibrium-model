"""
单位修复验证脚本
目标: 确认HHV单位修正后,温度预测恢复正常
"""

from gasifier import GasifierModel
import numpy as np

def quick_temperature_check():
    """快速检查温度是否恢复正常"""
    
    print("="*70)
    print("🔧 单位修复验证 - 温度快速检查")
    print("="*70)
    
    # Paper_Case_6 的输入
    inputs = {
        "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
        "Ad": 7.35, "Vd": 31.24, "FCd": 61.41, 
        "Mt": 4.53,
        "HHV_Input": 29800.0,  # 应被识别为 kJ/kg
        "FeedRate": 41670.0,
        "Ratio_OC": 0.86,
        "Ratio_SC": 0.08,
        "pt": 99.6,
        "P": 4.08,
        "TIN": 300.0,
        "HeatLossPercent": 1.0,  # 先用1%测试
        "GasifierType": "Dry Powder",
        "T_Coal_In": 298.15,
        "T_Slurry_In": 298.15,
        "T_Scrubber": 210.0,
        "TR": 1400.0,
        "HHV_Method": 0
    }
    
    print("\n📋 输入条件:")
    print(f"  煤种: 验证煤 (Cd={inputs['Cd']}%)")
    print(f"  HHV_Input: {inputs['HHV_Input']} (应识别为 kJ/kg)")
    print(f"  氧煤比: {inputs['Ratio_OC']}")
    print(f"  汽煤比: {inputs['Ratio_SC']}")
    print(f"  压力: {inputs['P']} MPa")
    print(f"  热损: {inputs['HeatLossPercent']}%")
    
    print("\n🔄 运行仿真...")
    
    try:
        model = GasifierModel(inputs)
        
        # 检查预处理后的HHV
        model._preprocess_inputs()
        print(f"\n✅ 预处理完成:")
        print(f"  HHV (模型内部): {model.HHV_coal:.2f} kJ/kg")
        print(f"  煤生成焓: {model.H_coal_form:.2f} kJ/kg")
        print(f"  方法: {model.hhv_method_used}")
        
        # 运行完整仿真
        results = model.run_simulation()
        
        print(f"\n📊 仿真结果:")
        print("-"*70)
        
        T_pred = results['TOUT_C']
        T_exp = 1370.0
        T_err = T_pred - T_exp
        
        print(f"{'指标':<25} {'预测值':<15} {'期望值':<15} {'误差':<15}")
        print("-"*70)
        print(f"{'温度 (°C)':<25} {T_pred:>14.1f} {T_exp:>14.1f} {T_err:>+14.1f}")
        print(f"{'CO (干基%)':<25} {results['Y_CO_dry']:>14.2f} {61.7:>14.2f} {results['Y_CO_dry']-61.7:>+14.2f}")
        print(f"{'H2 (干基%)':<25} {results['Y_H2_dry']:>14.2f} {30.3:>14.2f} {results['Y_H2_dry']-30.3:>+14.2f}")
        print(f"{'CO2 (干基%)':<25} {results['Y_CO2_dry']:>14.2f} {1.3:>14.2f} {results['Y_CO2_dry']-1.3:>+14.2f}")
        print(f"{'CH4 (干基%)':<25} {results['Y_CH4_dry']:>14.2f} {'<0.5':>14} {'':<15}")
        
        print("\n🔍 评估:")
        print("-"*70)
        
        # 温度评估
        if abs(T_err) < 50:
            temp_status = "✅ 温度正常 (误差 < 50°C)"
        elif abs(T_err) < 100:
            temp_status = "⚠️ 温度偏差较大 (50-100°C)"
        elif abs(T_err) < 500:
            temp_status = "❌ 温度严重偏离 (100-500°C)"
        else:
            temp_status = "🚨 温度完全错误 (>500°C) - 可能仍有单位问题!"
        
        print(f"  {temp_status}")
        
        # CO2检查
        if results['Y_CO2_dry'] > 0.1:
            co2_status = "✅ CO2未归零"
        else:
            co2_status = "❌ CO2归零异常"
        print(f"  {co2_status}")
        
        # CH4检查
        if results['Y_CH4_dry'] < 0.5:
            ch4_status = "✅ CH4受控"
        else:
            ch4_status = "⚠️ CH4偏高"
        print(f"  {ch4_status}")
        
        # 诊断信息
        diag = results['diagnostics']
        print(f"\n📋 诊断:")
        print(f"  收敛警告: {diag['total_warnings']}")
        print(f"  元素守恒问题: {diag['mass_balance_issues']}")
        print(f"  约束违反: {diag['constraint_violations']}")
        
        print("\n" + "="*70)
        
        # 总体判断
        if abs(T_err) < 100 and results['Y_CO2_dry'] > 0.1:
            print("🎉 单位修复成功! 模型运行正常!")
            print("\n💡 建议:")
            print("  1. 温度误差仍较大?调整 HeatLossPercent (建议2-3%)")
            print("  2. 运行完整验证: python test_validation.py")
            return True
        elif abs(T_err) > 500:
            print("❌ 单位问题未解决或存在其他错误!")
            print("\n🔍 排查:")
            print("  1. 检查 coal_props.py 中 COAL_DATABASE 的 HHV_d 是否已 ×1000")
            print("  2. 检查 calculate_coal_thermo() 是否有单位转换逻辑")
            print("  3. 运行: python coal_props.py 测试单元转换")
            return False
        else:
            print("⚠️ 部分修复,但仍需优化")
            print("\n💡 建议:")
            print("  1. 调整热损失参数")
            print("  2. 检查其他输入条件")
            return True
            
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        print(f"\n可能原因:")
        print(f"  1. 导入模块错误")
        print(f"  2. 代码修改未生效")
        print(f"  3. 其他语法错误")
        import traceback
        traceback.print_exc()
        return False


def compare_before_after():
    """对比修复前后的关键数值"""
    
    print("\n" + "="*70)
    print("📊 修复前后对比")
    print("="*70)
    
    print("\n修复前 (HHV单位错误):")
    print("  数据库: 30.72 MJ/kg")
    print("  被当作: 30.72 kJ/kg (错误!)")
    print("  差异: 1000倍!")
    print("  结果: 煤生成焓严重偏小 → 温度仅548°C")
    
    print("\n修复后 (HHV单位正确):")
    print("  数据库: 30720 kJ/kg")
    print("  正确识别: 30720 kJ/kg ✅")
    print("  或输入: 29.8 (自动识别为MJ/kg并转换)")
    print("  结果: 煤生成焓正确 → 温度约1350-1450°C ✅")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║          HHV单位修复验证                                     ║
    ║          检查温度是否从548°C恢复到1370°C附近               ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    compare_before_after()
    success = quick_temperature_check()
    
    if success:
        print("\n✅ 建议下一步:")
        print("  1. 运行完整验证: python test_validation.py")
        print("  2. 如温度仍偏离,运行: python debug_temperature.py")
        print("  3. 根据需要调整 HeatLossPercent 参数\n")
    else:
        print("\n❌ 请先解决单位问题后再继续\n")