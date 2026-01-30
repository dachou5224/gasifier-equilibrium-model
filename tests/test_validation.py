"""
验证测试脚本 - 测试优化后的气化炉模型
功能:
1. 运行所有验证案例
2. 对比模型预测 vs 文献数据
3. 检查收敛性诊断
4. 生成详细报告
"""

import sys
import os
import json
import numpy as np

# Add src to path (assuming script is in tests/, so ../src)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from gasifier.validation_cases import VALIDATION_CASES

class ValidationTester:
    def __init__(self):
        self.results = {}
        self.base_coal_data = None
        
    def _prepare_inputs(self, case_name, case_data):
        """准备输入数据,处理 SAME_AS_BASE 逻辑"""
        inputs = {}
        
        # 处理煤质数据
        coal_analysis = case_data['inputs']['Coal Analysis']
        if coal_analysis == "SAME_AS_BASE":
            if self.base_coal_data is None:
                raise ValueError(f"Case {case_name}: Base coal data not set!")
            coal_analysis = self.base_coal_data
        else:
            # 保存为base数据(如果是第一个完整案例)
            if self.base_coal_data is None:
                self.base_coal_data = coal_analysis.copy()
        
        # 合并所有输入
        inputs.update(coal_analysis)
        inputs.update(case_data['inputs']['Process Conditions'])
        
        # 设置默认值
        inputs.setdefault('T_Coal_In', 298.15)
        inputs.setdefault('T_Slurry_In', 298.15)
        inputs.setdefault('T_Scrubber', 210.0)
        inputs.setdefault('TR', 1400.0)  # 参考温度
        inputs.setdefault('HHV_Method', 0)  # 使用数据库值
        
        return inputs
    
    def _calculate_errors(self, predicted, expected):
        """计算预测误差"""
        errors = {}
        
        # 温度误差
        if 'TOUT_C' in expected:
            errors['T_error_C'] = predicted['TOUT_C'] - expected['TOUT_C']
            errors['T_error_pct'] = (errors['T_error_C'] / expected['TOUT_C']) * 100
        
        # 组分误差 (干基)
        comp_map = {
            'YCO': 'Y_CO_dry',
            'YH2': 'Y_H2_dry',
            'YCO2': 'Y_CO2_dry',
            'YCH4': 'Y_CH4_dry'
        }
        
        for exp_key, pred_key in comp_map.items():
            if exp_key in expected:
                errors[f'{exp_key}_error'] = predicted[pred_key] - expected[exp_key]
                errors[f'{exp_key}_error_pct'] = (errors[f'{exp_key}_error'] / expected[exp_key]) * 100
        
        return errors
    
    def _evaluate_performance(self, errors, diagnostics):
        """评估模型性能"""
        score = {
            'temperature': 'UNKNOWN',
            'composition': 'UNKNOWN',
            'convergence': 'UNKNOWN',
            'overall': 'UNKNOWN'
        }
        
        # 温度评估
        if 'T_error_C' in errors:
            T_err = abs(errors['T_error_C'])
            if T_err < 10:
                score['temperature'] = 'EXCELLENT'
            elif T_err < 30:
                score['temperature'] = 'GOOD'
            elif T_err < 50:
                score['temperature'] = 'ACCEPTABLE'
            else:
                score['temperature'] = 'POOR'
        
        # 组分评估 (主要看CO和H2)
        comp_errors = []
        for key in ['YCO_error', 'YH2_error']:
            if key in errors:
                comp_errors.append(abs(errors[key]))
        
        if comp_errors:
            avg_comp_err = np.mean(comp_errors)
            if avg_comp_err < 1.5:
                score['composition'] = 'EXCELLENT'
            elif avg_comp_err < 3.0:
                score['composition'] = 'GOOD'
            elif avg_comp_err < 5.0:
                score['composition'] = 'ACCEPTABLE'
            else:
                score['composition'] = 'POOR'
        
        # 收敛性评估
        total_issues = (diagnostics['total_warnings'] + 
                       diagnostics['mass_balance_issues'] + 
                       diagnostics['constraint_violations'])
        
        if total_issues == 0:
            score['convergence'] = 'PERFECT'
        elif total_issues <= 2:
            score['convergence'] = 'GOOD'
        elif total_issues <= 5:
            score['convergence'] = 'ACCEPTABLE'
        else:
            score['convergence'] = 'POOR'
        
        # 综合评估
        scores_map = {'EXCELLENT': 4, 'PERFECT': 4, 'GOOD': 3, 
                     'ACCEPTABLE': 2, 'POOR': 1, 'UNKNOWN': 0}
        
        score_values = [scores_map.get(score['temperature'], 0),
                       scores_map.get(score['composition'], 0),
                       scores_map.get(score['convergence'], 0)]
        
        avg_score = np.mean([s for s in score_values if s > 0])
        
        if avg_score >= 3.5:
            score['overall'] = 'EXCELLENT'
        elif avg_score >= 2.5:
            score['overall'] = 'GOOD'
        elif avg_score >= 1.5:
            score['overall'] = 'ACCEPTABLE'
        else:
            score['overall'] = 'POOR'
        
        return score
    
    def run_single_case(self, case_name, case_data, verbose=True, calibrate_heat_loss=True):
        """运行单个验证案例
        
        参数:
            calibrate_heat_loss: 是否自动校准热损以匹配目标温度（默认True）
        """
        if verbose:
            print("\n" + "="*70)
            print(f"🧪 测试案例: {case_name}")
            print(f"📝 描述: {case_data.get('description', 'N/A')}")
            print("="*70)
        
        try:
            # 准备输入
            inputs = self._prepare_inputs(case_name, case_data)
            
            # 创建模型
            model = GasifierModel(inputs)
            
            # 热损自动校准 (如果有目标温度)
            expected = case_data.get('expected_output', {})
            if calibrate_heat_loss and 'TOUT_C' in expected:
                target_T_K = expected['TOUT_C'] + 273.15
                try:
                    loss_pct, loss_J = model.calculate_heat_loss_for_target_T(target_T_K)
                    # 使用校准后的热损
                    model.inputs['HeatLossPercent'] = loss_pct
                    model._preprocess_inputs()
                    if verbose:
                        print(f"🔧 热损自动校准: {loss_pct:.2f}%")
                except Exception as e:
                    if verbose:
                        print(f"⚠️ 热损校准失败: {e}")
            
            # 运行仿真
            results = model.run_simulation()
            
            # 提取关键结果
            predicted = {
                'TOUT_C': results['TOUT_C'],
                'Y_CO_dry': results['Y_CO_dry'],
                'Y_H2_dry': results['Y_H2_dry'],
                'Y_CO2_dry': results['Y_CO2_dry'],
                'Y_CH4_dry': results['Y_CH4_dry'],
                'HHV': results['HHV'],
                'diagnostics': results['diagnostics']
            }
            
            # 计算误差
            expected = case_data.get('expected_output', {})
            errors = self._calculate_errors(predicted, expected)
            
            # 评估性能
            performance = self._evaluate_performance(errors, results['diagnostics'])
            
            # 汇总结果
            summary = {
                'case_name': case_name,
                'description': case_data.get('description', ''),
                'predicted': predicted,
                'expected': expected,
                'errors': errors,
                'performance': performance,
                'success': True
            }
            
            if verbose:
                self._print_case_summary(summary)
            
            return summary
            
        except Exception as e:
            error_summary = {
                'case_name': case_name,
                'description': case_data.get('description', ''),
                'error': str(e),
                'success': False
            }
            
            if verbose:
                print(f"\n❌ 案例运行失败: {e}\n")
            
            return error_summary
    
    def _print_case_summary(self, summary):
        """打印单个案例的结果摘要"""
        pred = summary['predicted']
        exp = summary['expected']
        err = summary['errors']
        perf = summary['performance']
        
        print("\n📊 结果对比:")
        print("-" * 70)
        
        # 温度
        if 'TOUT_C' in exp:
            print(f"{'温度 (°C)':<20} {'预测':<15} {'期望':<15} {'误差':<15}")
            print(f"{'':<20} {pred['TOUT_C']:>14.1f} {exp['TOUT_C']:>14.1f} {err.get('T_error_C', 0):>+14.1f}")
            print(f"{'温度评分':<20} {perf['temperature']}")
        
        # 组分
        print(f"\n{'组分 (干基%)':<20} {'预测':<15} {'期望':<15} {'误差':<15}")
        print("-" * 70)
        
        comp_pairs = [
            ('CO', 'YCO', 'Y_CO_dry'),
            ('H2', 'YH2', 'Y_H2_dry'),
            ('CO2', 'YCO2', 'Y_CO2_dry'),
            ('CH4', 'YCH4', 'Y_CH4_dry')
        ]
        
        for name, exp_key, pred_key in comp_pairs:
            if exp_key in exp:
                pred_val = pred[pred_key]
                exp_val = exp[exp_key]
                err_val = err.get(f'{exp_key}_error', 0)
                print(f"{name:<20} {pred_val:>14.2f} {exp_val:>14.2f} {err_val:>+14.2f}")
        
        print(f"\n{'组分评分':<20} {perf['composition']}")
        
        # 诊断信息
        diag = pred['diagnostics']
        print(f"\n🔍 诊断摘要:")
        print(f"   收敛警告: {diag['total_warnings']}")
        print(f"   元素守恒问题: {diag['mass_balance_issues']}")
        print(f"   约束违反: {diag['constraint_violations']}")
        print(f"   收敛性评分: {perf['convergence']}")
        
        # 总体评估
        print(f"\n{'='*70}")
        print(f"⭐ 总体评分: {perf['overall']}")
        print(f"{'='*70}")
    
    def run_all_cases(self, case_filter=None):
        """运行所有验证案例"""
        print("\n" + "🚀" + " 开始批量验证测试 " + "🚀".center(60, "="))
        
        cases_to_run = VALIDATION_CASES
        if case_filter:
            cases_to_run = {k: v for k, v in VALIDATION_CASES.items() 
                           if case_filter.lower() in k.lower()}
        
        if not cases_to_run:
            print(f"❌ 未找到匹配的案例 (过滤器: '{case_filter}')")
            return
        
        results_list = []
        
        for case_name, case_data in cases_to_run.items():
            result = self.run_single_case(case_name, case_data, verbose=True)
            results_list.append(result)
            self.results[case_name] = result
        
        # 生成总体报告
        self._print_overall_report(results_list)
        
        return results_list
    
    def _print_overall_report(self, results_list):
        """打印总体验证报告"""
        print("\n" + "="*70)
        print("📈 总体验证报告")
        print("="*70)
        
        successful = [r for r in results_list if r.get('success', False)]
        failed = [r for r in results_list if not r.get('success', False)]
        
        print(f"\n总案例数: {len(results_list)}")
        print(f"成功: {len(successful)} ✅")
        print(f"失败: {len(failed)} ❌")
        
        if not successful:
            print("\n⚠️  所有案例均失败,无法生成统计数据")
            return
        
        # 温度误差统计
        temp_errors = [abs(r['errors']['T_error_C']) 
                      for r in successful if 'T_error_C' in r['errors']]
        
        if temp_errors:
            print(f"\n🌡️  温度预测统计:")
            print(f"   平均绝对误差: {np.mean(temp_errors):.1f} °C")
            print(f"   最大误差: {np.max(temp_errors):.1f} °C")
            print(f"   最小误差: {np.min(temp_errors):.1f} °C")
        
        # 组分误差统计
        co_errors = [abs(r['errors']['YCO_error']) 
                    for r in successful if 'YCO_error' in r['errors']]
        h2_errors = [abs(r['errors']['YH2_error']) 
                    for r in successful if 'YH2_error' in r['errors']]
        
        if co_errors:
            print(f"\n⚗️  CO组分预测统计:")
            print(f"   平均绝对误差: {np.mean(co_errors):.2f} %")
        
        if h2_errors:
            print(f"\n💨 H2组分预测统计:")
            print(f"   平均绝对误差: {np.mean(h2_errors):.2f} %")
        
        # 收敛性统计
        total_warnings = sum(r['predicted']['diagnostics']['total_warnings'] 
                           for r in successful)
        total_mass_issues = sum(r['predicted']['diagnostics']['mass_balance_issues'] 
                              for r in successful)
        total_constraints = sum(r['predicted']['diagnostics']['constraint_violations'] 
                              for r in successful)
        
        print(f"\n🔍 收敛性统计 (所有案例总计):")
        print(f"   收敛警告: {total_warnings}")
        print(f"   元素守恒问题: {total_mass_issues}")
        print(f"   约束违反: {total_constraints}")
        
        # 评分分布
        overall_scores = [r['performance']['overall'] for r in successful]
        score_counts = {score: overall_scores.count(score) 
                       for score in ['EXCELLENT', 'GOOD', 'ACCEPTABLE', 'POOR']}
        
        print(f"\n⭐ 评分分布:")
        for score, count in score_counts.items():
            if count > 0:
                print(f"   {score}: {count} 案例")
        
        print("\n" + "="*70)
    
    def export_results(self, filename='validation_results.json'):
        """导出结果到JSON文件"""
        # 清理numpy类型以便JSON序列化
        def convert(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj
        
        clean_results = {}
        for case, result in self.results.items():
            clean_results[case] = {
                k: convert(v) for k, v in result.items()
            }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(clean_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 结果已导出到: {filename}")


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║     气流床气化炉模型 - 验证测试程序 (优化版)                ║
    ║     测试 #3 收敛性诊断 + #4 CO2约束                          ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    tester = ValidationTester()
    
    # 选项1: 运行所有案例
    print("🎯 选项: 运行所有验证案例\n")
    results = tester.run_all_cases()
    
    # 选项2: 运行特定案例 (注释掉上面,取消注释下面)
    # print("🎯 选项: 运行校准案例\n")
    # results = tester.run_all_cases(case_filter="Calibrated")
    
    # 导出结果
    tester.export_results('validation_results.json')
    
    print("\n✅ 验证测试完成!")
    print("\n💡 提示:")
    print("   - 查看详细诊断信息以了解收敛性问题")
    print("   - 温度误差 > 50°C 可能需要调整热损失参数")
    print("   - CO2含量现在应该稳定在 0.5-5% 范围内")
    print("   - 检查是否还有 'CO2归零' 现象\n")