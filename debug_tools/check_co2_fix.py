"""
CO2归零问题专项检查
测试修复效果: #4 CO2下限约束
"""

import sys
import os

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
import numpy as np

def check_co2_fix():
    """检查CO2归零问题是否被修复"""
    
    print("="*70)
    print("🔬 CO2归零问题专项检查")
    print("="*70)
    
    # 测试场景: 高温 + 高压 (最容易触发CO2归零)
    test_cases = [
        {
            "name": "高温场景 (1600°C理论)",
            "inputs": {
                # 煤质 (高挥发分 -> 高温)
                "Cd": 82.0, "Hd": 5.2, "Od": 8.5, "Nd": 1.0, "Sd": 0.3,
                "Ad": 6.0, "Vd": 35.0, "FCd": 59.0, "Mt": 8.0,
                "HHV_Input": 31000.0,
                # 工况 (高氧比 -> 高温)
                "FeedRate": 1000.0,
                "Ratio_OC": 1.05,  # 高氧比
                "Ratio_SC": 0.05,  # 低汽比
                "pt": 99.5,
                "P": 4.0,
                "TIN": 400.0,  # 高预热
                "HeatLossPercent": 0.5,  # 低热损
                "GasifierType": "Dry Powder"
            },
            "expected_T_range": (1550, 1700),
            "expected_CO2_min": 0.3  # 至少0.3%
        },
        {
            "name": "超高压场景",
            "inputs": {
                "Cd": 78.0, "Hd": 4.5, "Od": 11.0, "Nd": 0.9, "Sd": 0.6,
                "Ad": 8.0, "Vd": 30.0, "FCd": 62.0, "Mt": 6.0,
                "HHV_Input": 29000.0,
                "FeedRate": 1000.0,
                "Ratio_OC": 0.92,
                "Ratio_SC": 0.10,
                "pt": 99.0,
                "P": 6.5,  # 超高压
                "TIN": 350.0,
                "HeatLossPercent": 1.5,
                "GasifierType": "Dry Powder"
            },
            "expected_T_range": (1350, 1500),
            "expected_CO2_min": 0.5
        },
        {
            "name": "标准工况 (对照组)",
            "inputs": {
                "Cd": 75.83, "Hd": 4.58, "Od": 10.89, "Nd": 1.19, "Sd": 0.29,
                "Ad": 7.22, "Vd": 34.96, "FCd": 57.82, "Mt": 14.3,
                "HHV_Input": 30720.0,
                "FeedRate": 1000.0,
                "Ratio_OC": 0.88,
                "Ratio_SC": 0.12,
                "pt": 99.5,
                "P": 4.0,
                "TIN": 350.0,
                "HeatLossPercent": 1.8,
                "GasifierType": "Dry Powder"
            },
            "expected_T_range": (1350, 1450),
            "expected_CO2_min": 1.0
        }
    ]
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{'─'*70}")
        print(f"📋 测试 {i}/3: {case['name']}")
        print(f"{'─'*70}")
        
        try:
            model = GasifierModel(case['inputs'])
            output = model.run_simulation()
            
            # 提取关键数据
            T_out = output['TOUT_C']
            CO2_pct = output['Y_CO2_dry']
            CO_pct = output['Y_CO_dry']
            
            # 检查CO2是否归零
            is_co2_zero = CO2_pct < 0.1
            is_co2_abnormal = CO2_pct < case['expected_CO2_min']
            
            # 检查温度范围
            T_min, T_max = case['expected_T_range']
            is_T_normal = T_min <= T_out <= T_max
            
            # 结果判定
            status = "✅ 通过" if not is_co2_zero else "❌ 失败"
            
            print(f"\n结果:")
            print(f"  温度: {T_out:.1f}°C {'✅' if is_T_normal else '⚠️ 超出预期范围'}")
            print(f"  CO2: {CO2_pct:.3f}% {'✅ 正常' if not is_co2_abnormal else '⚠️ 偏低'}")
            print(f"  CO: {CO_pct:.2f}%")
            print(f"  CO/CO2比: {CO_pct/CO2_pct:.1f}")
            
            # 诊断信息
            diag = output['diagnostics']
            if diag['constraint_violations'] > 0:
                print(f"\n  ⚠️  约束违反: {diag['constraint_violations']}项")
                for msg in diag['details']['constraint_violations'][:3]:
                    print(f"     - {msg}")
            
            if is_co2_zero:
                print(f"\n  ❌ CO2归零异常! (< 0.1%)")
            elif is_co2_abnormal:
                print(f"\n  ⚠️  CO2低于预期 (< {case['expected_CO2_min']}%)")
            else:
                print(f"\n  ✅ CO2水平正常")
            
            results.append({
                'case': case['name'],
                'status': status,
                'T': T_out,
                'CO2': CO2_pct,
                'is_zero': is_co2_zero,
                'is_abnormal': is_co2_abnormal
            })
            
        except Exception as e:
            print(f"\n❌ 运行失败: {e}")
            results.append({
                'case': case['name'],
                'status': "❌ 异常",
                'error': str(e)
            })
    
    # 总结
    print(f"\n{'='*70}")
    print("📊 CO2修复效果总结")
    print(f"{'='*70}")
    
    total = len(results)
    passed = sum(1 for r in results if not r.get('is_zero', True))
    
    print(f"\n总测试数: {total}")
    print(f"CO2归零修复: {passed}/{total} 案例 {'✅' if passed == total else '❌'}")
    
    if passed == total:
        print(f"\n🎉 恭喜! CO2归零问题已完全修复!")
        print(f"   所有案例CO2含量 > 0.1%")
    else:
        print(f"\n⚠️  仍有 {total - passed} 案例存在CO2归零")
    
    # 详细列表
    print(f"\n详细结果:")
    for r in results:
        if 'error' in r:
            print(f"  {r['case']}: {r['status']} - {r['error']}")
        else:
            print(f"  {r['case']}: CO2={r['CO2']:.3f}% @ T={r['T']:.0f}°C {r['status']}")
    
    print(f"\n{'='*70}\n")
    
    return results


def compare_with_without_fix():
    """
    对比修复前后的差异 (如果您有旧版本代码)
    这里仅展示概念,实际需要调用旧版gasifier
    """
    print("💡 提示: 要对比修复前后,请:")
    print("   1. 保存一份gasifier.py的旧版本(未添加CO2下限)")
    print("   2. 在旧版中运行相同工况")
    print("   3. 对比CO2含量差异\n")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║          CO2归零问题专项检查                                 ║
    ║          验证 #4 CO2下限约束的修复效果                       ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    results = check_co2_fix()
    
    print("💡 后续建议:")
    print("   1. 如果所有案例通过 -> 修复成功!")
    print("   2. 如果仍有归零 -> 检查NIST高温系数是否正确加载")
    print("   3. 如果CO2偏低(<0.5%) -> 可能需要提高下限至 1%碳")
    print("   4. 运行完整验证: python test_validation.py\n")