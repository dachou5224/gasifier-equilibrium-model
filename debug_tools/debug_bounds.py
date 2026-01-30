#!/usr/bin/env python
"""诊断脚本: 调试边界违反问题"""
import numpy as np
import sys
sys.path.insert(0, '/Users/liuzhen/AI-projects/gasifier-model')
from gasifier import GasifierModel
from validation_cases import VALIDATION_CASES

# 测试 Paper_Case_6
case = VALIDATION_CASES['Paper_Case_6 (Calibrated)']
inputs = {}
inputs.update(case['inputs']['Coal Analysis'])
inputs.update(case['inputs']['Process Conditions'])

model = GasifierModel(inputs)
model._preprocess_inputs()

n_C_in, n_H_in, n_O_in, n_N_in, n_S_in = model.atom_input
print('元素输入:')
print(f'  C: {n_C_in:.4f}')
print(f'  H: {n_H_in:.4f}')
print(f'  O: {n_O_in:.4f}')
print(f'  N: {n_N_in:.4f}')
print(f'  S: {n_S_in:.4f}')

# 边界条件
co2_min = max(1e-10, n_C_in * 0.005)
ch4_limit = n_C_in * 0.005
print(f'\n边界条件:')
print(f'  CO2 下限: {co2_min:.4f}')
print(f'  CH4 上限: {ch4_limit:.4f}')

# 初值生成
for strategy in ['reducing', 'balanced', 'oxidizing']:
    n0 = model._generate_initial_guess(1000, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, strategy)
    print(f'\n{strategy} 策略初值:')
    
    # 边界检查
    bounds = [
        (1e-10, np.inf),      # CO
        (1e-10, np.inf),      # H2
        (co2_min, np.inf),    # CO2 - 保留下限
        (1e-10, ch4_limit),   # CH4 - 保留上限
        (1e-10, np.inf),      # H2O
        (1e-10, np.inf),      # N2
        (1e-10, np.inf),      # H2S
        (1e-10, np.inf)       # COS
    ]
    
    violations = []
    for i, (lb, ub) in enumerate(bounds):
        val = n0[i]
        if val < lb:
            violations.append(f'{model.species_list[i]}: {val:.6f} < {lb:.6f}')
        elif ub != np.inf and val > ub:
            violations.append(f'{model.species_list[i]}: {val:.6f} > {ub:.6f}')
    
    if violations:
        print('  边界违反:')
        for v in violations:
            print(f'    {v}')
    else:
        print('  全部通过边界检查')
