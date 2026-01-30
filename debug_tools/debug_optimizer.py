#!/usr/bin/env python
"""诊断脚本: 跟踪优化器在各策略下的行为"""
import numpy as np
import sys
sys.path.insert(0, '/Users/liuzhen/AI-projects/gasifier-model')
from gasifier import GasifierModel
from validation_cases import VALIDATION_CASES
from scipy.optimize import minimize
from thermo_data import get_gibbs_free_energy, R_CONST

# 测试 Paper_Case_6
case = VALIDATION_CASES['Paper_Case_6 (Calibrated)']
inputs = {}
inputs.update(case['inputs']['Coal Analysis'])
inputs.update(case['inputs']['Process Conditions'])

model = GasifierModel(inputs)
model._preprocess_inputs()

n_C_in, n_H_in, n_O_in, n_N_in, n_S_in = model.atom_input

T = 1600  # 典型气化温度

print(f"测试温度: {T}K ({T-273.15:.1f}°C)")
print(f"元素输入: C={n_C_in:.1f}, H={n_H_in:.1f}, O={n_O_in:.1f}")
print()

# 测试各策略
for strategy in ['reducing', 'balanced', 'oxidizing']:
    n0 = model._generate_initial_guess(T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, strategy)
    
    print(f"=== 策略: {strategy} ===")
    print(f"初值 H2: {n0[1]:.4f} mol")
    print(f"初值 CO: {n0[0]:.4f} mol")
    
    # 简化版求解
    co2_min = max(1e-10, n_C_in * 0.005)
    bounds = [
        (1e-10, np.inf),      # CO
        (1e-10, np.inf),      # H2
        (co2_min, np.inf),    # CO2
        (1e-10, np.inf),      # CH4
        (1e-10, np.inf),      # H2O
        (1e-10, np.inf),      # N2
        (1e-10, np.inf),      # H2S
        (1e-10, np.inf)       # COS
    ]
    
    G0_vals = np.array([get_gibbs_free_energy(s, T) for s in model.species_list])
    
    # 元素守恒约束
    cons = []
    for i in range(5):
        cons.append({
            'type': 'eq',
            'fun': lambda n, idx=i: np.dot(n, model.atom_matrix[idx]) - model.atom_input[idx]
        })
    
    try:
        res = minimize(
            model._gibbs_objective,
            n0,
            args=(G0_vals, model.P_ratio, T),
            method='SLSQP',
            bounds=bounds,
            constraints=cons,
            tol=1e-6,
            options={'maxiter': 500}
        )
        
        print(f"优化成功: {res.success}")
        print(f"输出 H2: {res.x[1]:.4f} mol")
        print(f"输出 CO: {res.x[0]:.4f} mol")
        print(f"输出 H2O: {res.x[4]:.4f} mol")
        print(f"Gibbs能: {res.fun:.2e}")
        
        # 检查元素守恒
        C_out = res.x[0] + res.x[2] + res.x[3] + res.x[7]
        H_out = 2*res.x[1] + 2*res.x[4] + 2*res.x[6] + 4*res.x[3]
        print(f"碳平衡: {C_out/n_C_in*100:.1f}%")
        print(f"氢平衡: {H_out/n_H_in*100:.1f}%")
        
    except Exception as e:
        print(f"求解失败: {e}")
    
    print()
